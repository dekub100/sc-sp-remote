import {
  action,
  KeyAction,
  KeyUpEvent,
  SingletonAction,
  WillAppearEvent,
  WillDisappearEvent,
} from "@elgato/streamdeck";
import { wsManager } from "../websocket-manager";

type ToggleRepeatSettings = {
  state?: number;
};

@action({ UUID: "com.dekub.spicetify-remote.togglerepeat" })
export class ToggleRepeat extends SingletonAction<ToggleRepeatSettings> {
  private actionContext: KeyAction<ToggleRepeatSettings> | null = null;

  private handleMessage = (data: any) => {
    // repeatStatus: 0 = off, 1 = context, 2 = track
    if (typeof data.repeatStatus === "number" && this.actionContext) {
      this.actionContext.setState(data.repeatStatus);
      this.actionContext.setSettings({ state: data.repeatStatus });
    }
  };

  override onWillAppear(
    ev: WillAppearEvent<ToggleRepeatSettings>
  ): void | Promise<void> {
    this.actionContext = ev.action as KeyAction<ToggleRepeatSettings>;
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
    ev: WillDisappearEvent<ToggleRepeatSettings>
  ): void | Promise<void> {
    wsManager.off("message", this.handleMessage);
    wsManager.disconnect();
    this.actionContext = null;
  }

  override async onKeyUp(
    ev: KeyUpEvent<ToggleRepeatSettings>
  ): Promise<void> {
    wsManager.send({ type: "playbackControl", command: "toggleRepeat" });
  }
}
