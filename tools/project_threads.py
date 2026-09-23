import json

from agent import AgentContext, AgentContextType
from helpers import persist_chat, plugins, projects
from helpers.state_monitor_integration import mark_dirty_all
from helpers.tool import Response, Tool
from initialize import initialize_agent


def linked_threads(project: str, excluded_id: str) -> list[AgentContext]:
    return sorted(
        (
            chat for chat in AgentContext.all()
            if chat.id != excluded_id
            and chat.type == AgentContextType.USER
            and projects.get_context_project_name(chat) == project
        ),
        key=lambda chat: chat.last_message,
        reverse=True,
    )


def conversation(chat: AgentContext) -> list[tuple[str, str]]:
    result = []
    for message in chat.agent0.history.all_messages():
        content = message.content
        if message.ai:
            try:
                response = json.loads(content) if isinstance(content, str) else content
            except ValueError:
                continue
            if isinstance(response, dict) and response.get("tool_name") == "response":
                args = response.get("tool_args")
                text = args.get("text") if isinstance(args, dict) else None
                if isinstance(text, str) and text:
                    result.append(("Assistant", text))
        elif isinstance(content, dict):
            text = content.get("user_message") or content.get("user_intervention")
            if isinstance(text, str) and text:
                result.append(("User", text))
    return result


def transcript(chat: AgentContext) -> str:
    return "\n\n".join(
        f"[{index}] {role}: {text}"
        for index, (role, text) in enumerate(conversation(chat), 1)
    )


class ProjectThreads(Tool):
    async def execute(
        self, action: str = "list", chat_id: str = "", query: str = "", offset: int = 0,
        title: str = "", **kwargs
    ) -> Response:
        project = self.agent.context.get_data("project_manager_project")
        if not project or projects.get_context_project_name(self.agent.context) != project:
            return Response(message="This tool is available only in a Project Manager chat.", break_loop=False)
        if action not in {"list", "read", "search", "create"}:
            return Response(message="Use list, read, search, or create.", break_loop=False)
        try:
            offset = int(offset)
            if not 0 <= offset <= 10_000_000:
                raise ValueError
        except (TypeError, ValueError):
            return Response(message="offset must be a nonnegative integer up to 10000000.", break_loop=False)

        if action == "create":
            settings = plugins.get_plugin_config("project_manager", agent=self.agent) or {}
            if settings.get("allow_thread_creation") is not True:
                return Response(message="New thread creation is disabled in Project Manager settings.", break_loop=False)
            if not isinstance(title, str) or not 1 <= len(title.strip()) <= 200:
                return Response(message="title must contain 1-200 characters.", break_loop=False)
            try:
                projects.load_basic_project_data(project)
            except (FileNotFoundError, ValueError) as error:
                return Response(message=str(error), break_loop=False)
            chat = AgentContext(config=initialize_agent(), name=title.strip())
            try:
                projects.activate_project(chat.id, project, mark_dirty=False)
            except Exception:
                AgentContext.remove(chat.id)
                persist_chat.remove_chat(chat.id)
                raise
            mark_dirty_all(reason="project_manager.create_thread")
            return Response(message=f"Created project thread '{chat.name}' with ID {chat.id}.", break_loop=False)

        threads = linked_threads(project, self.agent.context.id)
        if action == "list":
            page = threads[offset:offset + 50]
            lines = [f"{chat.id}: {chat.name or f'Chat {chat.id}'}" for chat in page]
            return Response(
                message=f"{len(threads)} linked threads; showing {offset + 1}-{offset + len(page)}.\n"
                + ("\n".join(lines) or "No threads on this page.")
                + (f"\nNext offset: {offset + len(page)}" if offset + len(page) < len(threads) else ""),
                break_loop=False,
            )
        if action == "read":
            chat = next((item for item in threads if item.id == chat_id), None)
            if chat is None:
                return Response(message="Linked thread not found.", break_loop=False)
            text = transcript(chat)
            chunk = text[offset:offset + 12_000]
            return Response(
                message=f"Thread: {chat.name or chat.id} ({chat.id})\nCharacters {offset}-{offset + len(chunk)} of {len(text)}\n\n{chunk}"
                + (f"\n\nNext offset: {offset + len(chunk)}" if offset + len(chunk) < len(text) else ""),
                break_loop=False,
            )
        query = str(query or "").strip()
        if not 2 <= len(query) <= 200:
            return Response(message="query must contain 2-200 characters.", break_loop=False)
        needle = query.casefold()
        matches = []
        for chat in threads:
            for role, text in conversation(chat):
                at = text.casefold().find(needle)
                if at >= 0:
                    excerpt = text[max(0, at - 180):at + len(query) + 180]
                    matches.append(f"{chat.id} · {chat.name or f'Chat {chat.id}'} · {role}: …{excerpt}…")
        page = matches[offset:offset + 15]
        return Response(
            message=f"{len(matches)} matches; showing {offset + 1}-{offset + len(page)}.\n"
            + ("\n\n".join(page) or "No matches on this page.")
            + (f"\nNext offset: {offset + len(page)}" if offset + len(page) < len(matches) else ""),
            break_loop=False,
        )
