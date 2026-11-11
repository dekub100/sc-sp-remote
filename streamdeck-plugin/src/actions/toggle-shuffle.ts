import {
  action,
  KeyAction,
  KeyUpEvent,
  SingletonAction,
  WillAppearEvent,
  WillDisappearEvent,
  DidReceiveSettingsEvent,
} from "@elgato/streamdeck";
import { wsManager } from "../websocket-manager";

type ToggleShuffleSettings = {
  state?: number;
  source?: string;
};

@action({ UUID: "com.dekub.sc-sp-remote.toggleshuffle" })
export class ToggleShuffle extends SingletonAction<ToggleShuffleSettings> {
  private actionContext: KeyAction<ToggleShuffleSettings> | null = null;
  private currentSource: string = "spotify";

  private handleMessage = (data: any) => {
    if (!this.actionContext) return;
    const source = this.currentSource;
    const effectiveSource = source === "auto" ? wsManager.activeSource : source;

    const state = data.state || {};
    if (data.source === effectiveSource && typeof state.isShuffling === "boolean") {
      const newState = state.isShuffling ? 1 : 0;
      this.actionContext.setState(newState);
      this.actionContext.setSettings({ state: newState, source });
    }
  };

  override async onWillAppear(
    ev: WillAppearEvent<ToggleShuffleSettings>
  ): Promise<void> {
    this.actionContext = ev.action as KeyAction<ToggleShuffleSettings>;
    const settings = await ev.action.getSettings();
    this.currentSource = settings.source || "spotify";

    wsManager.connect();
    wsManager.on("message", this.handleMessage);

    if (wsManager.readyState === 1) {
        wsManager.requestState();
    } else {
        wsManager.once("open", () => wsManager.requestState());
    }
  }

  override onWillDisappear(
    ev: WillDisappearEvent<ToggleShuffleSettings>
  ): void | Promise<void> {
    wsManager.off("message", this.handleMessage);
    wsManager.disconnect();
    this.actionContext = null;
  }

  override async onDidReceiveSettings(ev: DidReceiveSettingsEvent<ToggleShuffleSettings>): Promise<void> {
    this.currentSource = ev.payload.settings.source || "spotify";
  }

  override async onKeyUp(
    ev: KeyUpEvent<ToggleShuffleSettings>
  ): Promise<void> {
    const source = ev.payload.settings.source || "spotify";
    const effectiveSource = source === "auto" ? wsManager.activeSource : source;
    wsManager.sendCommand(effectiveSource, "toggleShuffle");
  }
}
