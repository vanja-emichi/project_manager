import asyncio
import json
import threading
from types import SimpleNamespace

from agent import AgentContextType
from usr.plugins.project_manager.api import open_project
from usr.plugins.project_manager.extensions.python.system_prompt import _20_project_manager
from usr.plugins.project_manager.tools import project_threads


def make_chat(id, project, name, messages=(), manager=False):
    data = {"project": project}
    output_data = {}
    if manager:
        data["project_manager_project"] = project
    config = SimpleNamespace(profile="agent0")
    chat = SimpleNamespace(
        id=id, type=AgentContextType.USER, name=name, data=data, output_data=output_data,
        last_message=id, config=config,
        agent0=SimpleNamespace(config=config, history=SimpleNamespace(all_messages=lambda: [
            SimpleNamespace(ai=kind == "response", content=(
                '{"tool_name":"response","tool_args":{"text":' + json.dumps(text) + "}}"
                if kind == "response" else {"user_message": text}
            )) for kind, text in messages
        ])),
    )
    chat.get_data = data.get
    chat.set_data = data.__setitem__
    chat.get_output_data = output_data.get
    chat.set_output_data = output_data.__setitem__
    chat.is_running = lambda: False
    return chat


def test_open_reuses_project_chat_and_thread_access_is_scoped(monkeypatch):
    chats = [make_chat("a", "alpha", "Design", [("user", "Use teal"), ("response", "Agreed")]),
             make_chat("b", "beta", "Private", [("user", "secret teal")])]
    monkeypatch.setattr(open_project.AgentContext, "all", lambda: chats)
    monkeypatch.setattr(open_project.AgentContext, "generate_id", lambda: "manager")
    monkeypatch.setattr(open_project.projects, "load_basic_project_data", lambda name: {"title": "Alpha"})
    monkeypatch.setattr(open_project.projects, "activate_project", lambda id, name, **kw: None)
    monkeypatch.setattr(open_project.projects, "get_context_project_name", lambda chat: chat.data["project"])
    monkeypatch.setattr(project_threads.projects, "get_context_project_name", lambda chat: chat.data["project"])
    monkeypatch.setattr(open_project.plugins, "get_plugin_config", lambda *args, **kwargs: {
        "agent_profile": "researcher", "model_preset": "Fast",
    })
    monkeypatch.setattr(open_project.subagents, "get_available_agents_dict", lambda name: {"researcher": object()})
    monkeypatch.setattr(open_project.model_config, "resolve_preset", lambda name: {"name": "Fast"} if name == "Fast" else None)
    monkeypatch.setattr(open_project, "initialize_agent", lambda **kwargs: SimpleNamespace(profile="researcher"))
    saved = []
    monkeypatch.setattr(open_project.persist_chat, "save_tmp_chat", lambda chat: saved.append(chat.id))
    monkeypatch.setattr(open_project, "mark_dirty_all", lambda **kw: None)
    handler = open_project.OpenProject(None, threading.RLock())
    handler.use_context = lambda id: chats.append(make_chat(id, "alpha", "", manager=False)) or chats[-1]

    first = asyncio.run(handler.process({"project_name": "alpha"}, None))
    second = asyncio.run(handler.process({"project_name": "alpha"}, None))
    assert first == second == {"ok": True, "ctxid": "manager", "warning": ""}
    assert saved == ["manager"]
    assert chats[-1].config.profile == "researcher"
    assert chats[-1].get_data("chat_model_override") == {"preset_name": "Fast"}
    assert chats[-1].get_output_data("name") == "Alpha · Project"

    tool = project_threads.ProjectThreads(SimpleNamespace(context=chats[-1]), "project_threads", None, {}, "", None)
    assert "a: Design" in asyncio.run(tool.execute(action="list")).message
    assert "b: Private" not in asyncio.run(tool.execute(action="list")).message
    assert "Use teal" in asyncio.run(tool.execute(action="search", query="teal")).message
    assert "secret teal" not in asyncio.run(tool.execute(action="search", query="teal")).message
    assert "Use teal" in asyncio.run(tool.execute(action="read", chat_id="a")).message
    assert asyncio.run(tool.execute(action="read", chat_id="b")).message == "Linked thread not found."


def test_thread_creation_requires_project_setting(monkeypatch):
    manager = make_chat("manager", "alpha", "Alpha Project", manager=True)
    tool = project_threads.ProjectThreads(SimpleNamespace(context=manager), "project_threads", None, {}, "", None)
    settings = {"allow_thread_creation": False}
    monkeypatch.setattr(project_threads.plugins, "get_plugin_config", lambda *args, **kwargs: settings)
    monkeypatch.setattr(project_threads.projects, "get_context_project_name", lambda chat: chat.data["project"])
    assert "disabled" in asyncio.run(tool.execute(action="create", title="Plan")).message

    created = []
    monkeypatch.setattr(project_threads, "initialize_agent", lambda: manager.config)
    monkeypatch.setattr(project_threads, "AgentContext", lambda *, config, name: created.append(make_chat("new", "alpha", name)) or created[-1])
    monkeypatch.setattr(project_threads.projects, "load_basic_project_data", lambda name: {})
    monkeypatch.setattr(project_threads.projects, "activate_project", lambda id, name, **kwargs: None)
    monkeypatch.setattr(project_threads, "mark_dirty_all", lambda **kwargs: None)
    settings["allow_thread_creation"] = True
    assert "1-200" in asyncio.run(tool.execute(action="create", title=" ")).message
    assert "Created project thread 'Plan' with ID new." == asyncio.run(tool.execute(action="create", title=" Plan ")).message
    assert len(created) == 1


def test_custom_instructions_only_apply_to_manager_chat(monkeypatch):
    chat = make_chat("manager", "alpha", "Alpha Project", manager=True)
    agent = SimpleNamespace(context=chat)
    monkeypatch.setattr(_20_project_manager.projects, "get_context_project_name", lambda context: context.data["project"])
    monkeypatch.setattr(_20_project_manager.plugins, "get_plugin_config", lambda *args, **kwargs: {"instructions": "Prioritize open risks."})
    prompt = []
    extension = _20_project_manager.ProjectManagerPrompt(agent)
    asyncio.run(extension.execute(system_prompt=prompt))
    assert prompt[-1] == "Project Manager instructions:\nPrioritize open risks."
    chat.data.pop("project_manager_project")
    prompt = []
    asyncio.run(extension.execute(system_prompt=prompt))
    assert prompt == []
