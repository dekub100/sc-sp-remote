import { action, KeyDownEvent, SingletonAction } from "@elgato/streamdeck";
import { wsManager } from "../websocket-manager";

@action({ UUID: "com.dekub.spicetify-remote.previoustrack" })
export class PreviousTrack extends SingletonAction {
  override onWillAppear(): void | Promise<void> {
    wsManager.connect();
  }

  override onWillDisappear(): void | Promise<void> {
    wsManager.disconnect();
  }

  override async onKeyUp(ev: KeyUpEvent): Promise<void> {
    wsManager.send({ type: "playbackControl", command: "previous" });
  }
}
