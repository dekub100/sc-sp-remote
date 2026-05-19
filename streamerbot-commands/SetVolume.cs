using System;
using System.Globalization;

public class CPHInline
{
    public bool Execute()
    {
        object rawObj;
        if (!CPH.TryGetArg("volume", out rawObj) && !CPH.TryGetArg("rawInput", out rawObj))
        {
            CPH.SendMessage("Usage: !volume <0-100>");
            return false;
        }

        string input = rawObj.ToString().Trim();
        if (!int.TryParse(input, out int volPercent))
        {
            CPH.SendMessage("Invalid volume. Usage: !volume <0-100>");
            return false;
        }

        float vol = Math.Max(0.0f, Math.Min(1.0f, volPercent / 100.0f));
        string json = "{\"type\":\"volumeUpdate\",\"volume\":" + vol.ToString("0.00", CultureInfo.InvariantCulture) + "}";
        CPH.WebsocketSend(json, 0);
        CPH.SendMessage($"🔊 Volume set to {volPercent}%");
        return true;
    }
}
