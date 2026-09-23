# Project Manager

## Install

Install this directory as a community plugin from Git or ZIP in Agent Zero's Plugins UI, then enable the bundled **Sidebar Folders** plugin and its folder view. No additional packages, accounts, or paid services are needed.

In **Plugins → Project Manager → Settings**, choose the project in the scope selector. Set project manager instructions, allow or block new thread creation, and optionally choose its agent profile and model preset. Instructions apply on the next message; profile and preset changes apply when that chat is reopened while idle. Blank profile or preset selections keep the chat's current choice.

## Use

Open a persistent project chat from **Sidebar Folders → project folder → ⋮ → Chat with project**. The action appears only for named project folders, and requires the bundled Sidebar Folders plugin with folder view enabled.

The chat uses the project's ordinary Agent Zero instructions, files, tools, and model configuration. Its `project_threads` tool can list, search, and read the text of user messages and assistant replies in chats currently linked to that project, including parallel child chats. Results are paged so large projects do not fill the model context in one call. The project chat itself is excluded from linked-thread results. Attached images and files remain available through their original chats and project files; the thread reader covers text.

When thread creation is enabled for that project, the same tool can create a named, idle chat linked to the project. It does not send a message or start agent work. New threads use the project's normal profile and model defaults.

## Test

With the plugin at `usr/plugins/project_manager` in an Agent Zero checkout, run `python -m pytest usr/plugins/project_manager/tests/test_project_manager.py -q` from the checkout root using the framework Python environment.

## Remove

Uninstalling the plugin leaves existing project chats as ordinary chats; their transcripts are not deleted.
