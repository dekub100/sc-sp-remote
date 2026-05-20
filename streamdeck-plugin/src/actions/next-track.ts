import { action, KeyUpEvent, SingletonAction } from "@elgato/streamdeck";
import { wsManager } from "../websocket-manager";

@action({ UUID: "com.dekub.spicetify-remote.nexttrack" })
export class NextTrack extends SingletonAction {
  override onWillAppear(): void | Promise<void> {
    wsManager.connect();
  }

  override onWillDisappear(): void | Promise<void> {
    wsManager.disconnect();
  }

  override async onKeyUp(ev: KeyUpEvent): Promise<void> {
    wsManager.send({ type: "playbackControl", command: "next" });
  }
}
