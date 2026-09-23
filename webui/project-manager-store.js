import { createStore } from "/js/AlpineStore.js";
import { callJsonApi } from "/js/api.js";
import { toastFrontendError, toastFrontendWarning } from "/components/notifications/notification-store.js";
import { store as chats } from "/components/sidebar/chats/chats-store.js";
import { store as folders } from "/plugins/_sidebar_folders/webui/sidebar-folders-store.js";

export const store = createStore("projectManager", {
  busy: false,
  presets: [],
  async loadPresets() {
    try {
      const result = await callJsonApi("/plugins/_model_config/model_presets", { action: "get" });
      if (!result.ok) throw new Error("Could not load model presets");
      this.presets = (result.presets || []).map((preset) => preset.name).filter(Boolean);
    } catch (error) {
      void toastFrontendError(error?.message || "Could not load model presets", "Project Manager");
    }
  },
  async open() {
    const project = folders.menuProject;
    folders.closeMenu();
    if (!project || this.busy) return;
    this.busy = true;
    try {
      const result = await callJsonApi("/plugins/project_manager/open_project", { project_name: project });
      if (!result.ok) throw new Error("Could not open project chat");
      await chats.selectChat(result.ctxid);
      if (result.warning) void toastFrontendWarning(result.warning, "Project Manager");
    } catch (error) {
      void toastFrontendError(error?.message || "Could not open project chat", "Project Manager");
    } finally {
      this.busy = false;
    }
  },
});
