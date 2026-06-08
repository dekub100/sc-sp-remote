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

type PlayPauseSettings = {
  state?: number;
  source?: string;
};

@action({ UUID: "com.dekub.sc-sp-remote.playpause" })
export class PlayPause extends SingletonAction<PlayPauseSettings> {
  private actionInstances: Map<string, KeyAction<PlayPauseSettings>> = new Map();
  private actionSources: Map<string, string> = new Map();
  private lastPressTime: number = 0;

  private onMessage = (data: any) => {
    if (Date.now() - this.lastPressTime < 500) {
      return;
    }

    this.actionInstances.forEach((action, id) => {
      const source = this.actionSources.get(id) || "spotify";
      const effectiveSource = source === "auto" ? wsManager.activeSource : source;
      if (data.source === effectiveSource && typeof data.isPlaying === "boolean") {
        action.setState(data.isPlaying ? 1 : 0);
      }
    });
  };

  override async onWillAppear(
    ev: WillAppearEvent<PlayPauseSettings>
  ): Promise<void> {
    this.actionInstances.set(ev.action.id, ev.action as KeyAction<PlayPauseSettings>);
    const settings = await ev.action.getSettings();
    this.actionSources.set(ev.action.id, settings.source || "spotify");

    if (this.actionInstances.size === 1) {
      wsManager.connect();
      wsManager.on("message", this.onMessage);
    }

    if (settings.state !== undefined) {
      (ev.action as KeyAction<PlayPauseSettings>).setState(settings.state);
    }

    if (wsManager.readyState === 1) {
      wsManager.requestState();
    } else {
      wsManager.once("open", () => wsManager.requestState());
    }
  }

  override onWillDisappear(
    ev: WillDisappearEvent<PlayPauseSettings>
  ): void | Promise<void> {
    this.actionInstances.delete(ev.action.id);
    this.actionSources.delete(ev.action.id);
    if (this.actionInstances.size === 0) {
      wsManager.off("message", this.onMessage);
      wsManager.disconnect();
    }
  }

  override async onDidReceiveSettings(ev: DidReceiveSettingsEvent<PlayPauseSettings>): Promise<void> {
    this.actionSources.set(ev.action.id, ev.payload.settings.source || "spotify");
  }

  override async onKeyUp(ev: KeyUpEvent<PlayPauseSettings>): Promise<void> {
    this.lastPressTime = Date.now();
    const source = ev.payload.settings.source || "spotify";
    const effectiveSource = source === "auto" ? wsManager.activeSource : source;
    if (effectiveSource === "soundcloud") {
      wsManager.send({ type: "scPlaybackControl", command: "togglePlay" });
    } else {
      wsManager.send({ type: "playbackControl", command: "togglePlay" });
    }
  }
}
