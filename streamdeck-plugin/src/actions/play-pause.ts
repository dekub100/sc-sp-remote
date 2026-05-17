import {
  action,
  KeyAction,
  KeyUpEvent,
  SingletonAction,
  WillAppearEvent,
  WillDisappearEvent,
} from "@elgato/streamdeck";
import { wsManager } from "../websocket-manager";

type PlayPauseSettings = {
  state?: number;
};

@action({ UUID: "com.dekub.spicetify-remote.playpause" })
export class PlayPause extends SingletonAction<PlayPauseSettings> {
  private actionInstances: Map<string, KeyAction<PlayPauseSettings>> = new Map();
  private lastPressTime: number = 0;

  private onMessage = (data: any) => {
    // Ignore messages for 500ms after a physical press to avoid race conditions
    // where Spotify sends the "old" state before the toggle has completed.
    if (Date.now() - this.lastPressTime < 500) {
      return;
    }

    if (typeof data.isPlaying === "boolean") {
      const newState = data.isPlaying ? 1 : 0;
      this.actionInstances.forEach((action) => {
        action.setState(newState);
      });
    }
  };

  override onWillAppear(
    ev: WillAppearEvent<PlayPauseSettings>
  ): void | Promise<void> {
    this.actionInstances.set(ev.action.id, ev.action as KeyAction<PlayPauseSettings>);
    if (this.actionInstances.size === 1) {
      wsManager.connect();
      wsManager.on("message", this.onMessage);
    }
    
    if (ev.payload.settings.state !== undefined) {
      ev.action.setState(ev.payload.settings.state);
    }

    // Always request state when an action appears to ensure it has latest data
    if (wsManager.readyState === 1) {
      // WebSocket.OPEN
      wsManager.requestState();
    } else {
      wsManager.once("open", () => wsManager.requestState());
    }
  }

  override onWillDisappear(
    ev: WillDisappearEvent<PlayPauseSettings>
  ): void | Promise<void> {
    this.actionInstances.delete(ev.action.id);
    if (this.actionInstances.size === 0) {
      wsManager.off("message", this.onMessage);
      wsManager.disconnect();
    }
  }

  override async onKeyUp(ev: KeyUpEvent<PlayPauseSettings>): Promise<void> {
    this.lastPressTime = Date.now();
    wsManager.send({ type: "playbackControl", command: "togglePlay" });
  }
}
