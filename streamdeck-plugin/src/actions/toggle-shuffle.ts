import {
  action,
  KeyAction,
  KeyDownEvent,
  SingletonAction,
  WillAppearEvent,
  WillDisappearEvent,
} from "@elgato/streamdeck";
import { wsManager } from "../websocket-manager";

type ToggleShuffleSettings = {
  state?: number;
};

@action({ UUID: "com.dekub.spicetify-remote.toggleshuffle" })
export class ToggleShuffle extends SingletonAction<ToggleShuffleSettings> {
  private actionContext: KeyAction<ToggleShuffleSettings> | null = null;

  private handleMessage = (data: any) => {
    if (typeof data.isShuffling === "boolean" && this.actionContext) {
      const newState = data.isShuffling ? 1 : 0; // 0 for off, 1 for on
      this.actionContext.setState(newState);
      this.actionContext.setSettings({ state: newState });
    }
  };

  override onWillAppear(
    ev: WillAppearEvent<ToggleShuffleSettings>
  ): void | Promise<void> {
    this.actionContext = ev.action as KeyAction<ToggleShuffleSettings>;
    wsManager.connect();
    wsManager.on("message", this.handleMessage);

    // Always request state when an action appears to ensure it has latest data
    if (wsManager.readyState === 1) { // WebSocket.OPEN
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

  override async onKeyUp(
    ev: KeyUpEvent<ToggleShuffleSettings>
  ): Promise<void> {
    wsManager.send({ type: "playbackControl", command: "toggleShuffle" });
  }
}
