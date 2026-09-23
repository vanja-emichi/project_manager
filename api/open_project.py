from agent import AgentContext, AgentContextType
from helpers import persist_chat, plugins, projects, subagents
from helpers.api import ApiHandler, Input, Output, Request, Response
from helpers.state_monitor_integration import mark_dirty_all
from initialize import initialize_agent
from plugins._model_config.helpers import model_config


class OpenProject(ApiHandler):
    async def process(self, input: Input, request: Request) -> Output:
        name = input.get("project_name")
        if not isinstance(name, str):
            return Response("project_name must be a string", 400)
        try:
            projects.validate_project_name(name)
            project = projects.load_basic_project_data(name)
        except (ValueError, FileNotFoundError):
            return Response("Project not found", 404)

        settings = plugins.get_plugin_config("project_manager", project_name=name, agent_profile="") or {}
        profile = settings.get("agent_profile") or ""
        preset_name = settings.get("model_preset") or ""
        if not isinstance(profile, str) or not isinstance(preset_name, str):
            return Response("Invalid Project Manager settings", 400)
        if profile and profile not in subagents.get_available_agents_dict(name):
            return Response(f"Agent profile '{profile}' is unavailable in this project", 400)
        preset = model_config.resolve_preset(preset_name) if preset_name else None
        if preset_name and not preset:
            return Response(f"Model preset '{preset_name}' not found", 400)
        override = {"preset_name": str(preset["name"])} if preset else None
        profile_config = initialize_agent(override_settings={"agent_profile": profile}) if profile else None

        with self.thread_lock:
            context = next(
                (
                    chat for chat in AgentContext.all()
                    if chat.type == AgentContextType.USER
                    and chat.get_data("project_manager_project") == name
                    and projects.get_context_project_name(chat) == name
                ),
                None,
            )
            if context is None:
                context = self.use_context(AgentContext.generate_id())
                try:
                    projects.activate_project(context.id, name, mark_dirty=False)
                    context.set_data("project_manager_project", name)
                except Exception:
                    AgentContext.remove(context.id)
                    persist_chat.remove_chat(context.id)
                    raise
                created = True
            else:
                created = False

            warning = ""
            changed = created
            display_name = f"{project.get('title') or name} · Project"
            if created:
                context.name = display_name
            if context.get_output_data("name") != display_name:
                context.set_output_data("name", display_name)
                changed = True
            if context.is_running():
                if (profile and context.config.profile != profile) or (override and context.get_data("chat_model_override") != override):
                    warning = "Agent profile and model preset changes apply when this chat is idle and reopened."
            else:
                if profile_config and context.config.profile != profile:
                    context.config = context.agent0.config = profile_config
                    changed = True
                if override:
                    if context.get_data("chat_model_override") != override:
                        context.set_data("chat_model_override", override)
                        changed = True
            if changed:
                persist_chat.save_tmp_chat(context)
                mark_dirty_all(reason="project_manager.open_project")
        return {"ok": True, "ctxid": context.id, "warning": warning}
