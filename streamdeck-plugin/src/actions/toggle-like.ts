import {
  action,
  KeyAction,
  KeyUpEvent,
  SingletonAction,
  WillAppearEvent,
  WillDisappearEvent,
} from "@elgato/streamdeck";
import { wsManager } from "../websocket-manager";

type ToggleLikeSettings = {
  state?: number;
};

@action({ UUID: "com.dekub.spicetify-remote.togglelike" })
export class ToggleLike extends SingletonAction<ToggleLikeSettings> {
  private actionContext: KeyAction<ToggleLikeSettings> | null = null;

  private handleMessage = (data: any) => {
    if (typeof data.isLiked === "boolean" && this.actionContext) {
      const newState = data.isLiked ? 1 : 0; // 0 for not liked, 1 for liked
      this.actionContext.setState(newState);
      this.actionContext.setSettings({ state: newState });
    }
  };

  override onWillAppear(
    ev: WillAppearEvent<ToggleLikeSettings>
  ): void | Promise<void> {
    this.actionContext = ev.action as KeyAction<ToggleLikeSettings>;
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
    ev: WillDisappearEvent<ToggleLikeSettings>
  ): void | Promise<void> {
    wsManager.off("message", this.handleMessage);
    wsManager.disconnect();
    this.actionContext = null;
  }

  override async onKeyUp(
    ev: KeyUpEvent<ToggleLikeSettings>
  ): Promise<void> {
    wsManager.send({ type: "playbackControl", command: "like" });
  }
}
