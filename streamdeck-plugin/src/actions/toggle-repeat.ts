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

type ToggleRepeatSettings = {
  state?: number;
  source?: string;
};

@action({ UUID: "com.dekub.sc-sp-remote.togglerepeat" })
export class ToggleRepeat extends SingletonAction<ToggleRepeatSettings> {
  private actionContext: KeyAction<ToggleRepeatSettings> | null = null;
  private currentSource: string = "spotify";

  private handleMessage = (data: any) => {
    if (!this.actionContext) return;
    const source = this.currentSource;
    const effectiveSource = source === "auto" ? wsManager.activeSource : source;

    if (data.source === effectiveSource && typeof data.repeatStatus === "number") {
      this.actionContext.setState(data.repeatStatus);
      this.actionContext.setSettings({ state: data.repeatStatus, source });
    }
  };

  override async onWillAppear(
    ev: WillAppearEvent<ToggleRepeatSettings>
  ): Promise<void> {
    this.actionContext = ev.action as KeyAction<ToggleRepeatSettings>;
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
    ev: WillDisappearEvent<ToggleRepeatSettings>
  ): void | Promise<void> {
    wsManager.off("message", this.handleMessage);
    wsManager.disconnect();
    this.actionContext = null;
  }

  override async onDidReceiveSettings(ev: DidReceiveSettingsEvent<ToggleRepeatSettings>): Promise<void> {
    this.currentSource = ev.payload.settings.source || "spotify";
  }

  override async onKeyUp(
    ev: KeyUpEvent<ToggleRepeatSettings>
  ): Promise<void> {
    const source = ev.payload.settings.source || "spotify";
    const effectiveSource = source === "auto" ? wsManager.activeSource : source;
    if (effectiveSource === "soundcloud") {
      wsManager.send({ type: "scPlaybackControl", command: "toggleRepeat" });
    } else {
      wsManager.send({ type: "playbackControl", command: "toggleRepeat" });
    }
  }
}
