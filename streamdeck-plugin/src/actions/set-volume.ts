import { action, KeyUpEvent, SingletonAction, DidReceiveSettingsEvent, KeyAction, WillAppearEvent } from "@elgato/streamdeck";
import { wsManager } from "../websocket-manager";

interface SetVolumeSettings {
  volume: number; // The target volume level (0.0 to 1.0)
  [key: string]: any; // Add index signature to satisfy JsonObject constraint
}

@action({ UUID: "com.dekub.spicetify-remote.setvolume" })
export class SetVolume extends SingletonAction<SetVolumeSettings> {
    override async onWillAppear(ev: WillAppearEvent<SetVolumeSettings>): Promise<void> {
      wsManager.connect();
      const currentSettings = await ev.action.getSettings();
      this.updateDisplay(ev.action as KeyAction<SetVolumeSettings>, currentSettings);
    }
  
    override onWillDisappear(): void | Promise<void> {
      wsManager.disconnect();
    }
  
    override async onDidReceiveSettings(ev: DidReceiveSettingsEvent<SetVolumeSettings>): Promise<void> {
      const receivedSettings = ev.payload.settings;
      await ev.action.setSettings(receivedSettings);
      this.updateDisplay(ev.action as KeyAction<SetVolumeSettings>, receivedSettings);
    }
  
    override async onKeyUp(ev: KeyUpEvent<SetVolumeSettings>): Promise<void> {
      const volumeToSend = ev.payload.settings.volume !== undefined ? ev.payload.settings.volume : 0.5;
      wsManager.send({ type: "volumeUpdate", volume: volumeToSend });
    }
  
    private updateDisplay(action: KeyAction<SetVolumeSettings>, settings: SetVolumeSettings): void {
      if (action) {
        const volumePercentage = (settings.volume * 100).toFixed(0);
        action.setTitle(`${volumePercentage}%`);
      }
    }
  }
