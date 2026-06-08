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

@action({ UUID: "com.dekub.sc-sp-remote.togglerepeat" })
export class ToggleRepeat extends SingletonAction<ToggleRepeatSettings> {
  private actionContext: KeyAction<ToggleRepeatSettings> | null = null;

  private handleMessage = (data: any) => {
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

  override async onKeyUp(
    ev: KeyUpEvent<ToggleRepeatSettings>
  ): Promise<void> {
    wsManager.send({ type: "playbackControl", command: "toggleRepeat" });
  }
}
