import { action, KeyUpEvent, SingletonAction, WillAppearEvent, WillDisappearEvent, DidReceiveSettingsEvent } from "@elgato/streamdeck";
import { wsManager } from "../websocket-manager";

type VolumeDownSettings = {
  source?: string;
  step?: number;
};

@action({ UUID: "com.dekub.sc-sp-remote.volumedown" })
export class VolumeDown extends SingletonAction<VolumeDownSettings> {
  override onWillAppear(ev: WillAppearEvent<VolumeDownSettings>): void | Promise<void> {
    wsManager.connect();
  }

  override onWillDisappear(): void | Promise<void> {
    wsManager.disconnect();
  }

  override async onKeyUp(ev: KeyUpEvent<VolumeDownSettings>): Promise<void> {
    const source = ev.payload.settings.source || "spotify";
    const effectiveSource = source === "auto" ? wsManager.activeSource : source;
    const step = ev.payload.settings.step || 0.05;
    if (effectiveSource === "soundcloud") {
      wsManager.send({ type: "scVolumeUpdate", command: "volumeDown", step });
    } else {
      wsManager.send({ type: "volumeUpdate", command: "volumeDown", step });
    }
  }
}
