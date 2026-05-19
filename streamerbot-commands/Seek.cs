using System;

public class CPHInline
{
    public bool Execute()
    {
        object posObj;
        if (!CPH.TryGetArg("position", out posObj) && !CPH.TryGetArg("rawInput", out posObj))
        {
            CPH.SendMessage("Usage: !seek <seconds> or !seek <mm:ss>");
            return false;
        }

        string input = posObj.ToString().Trim();
        int ms = 0;

        int colon = input.IndexOf(':');
        if (colon > 0)
        {
            int mins, secs;
            if (int.TryParse(input.Substring(0, colon), out mins) &&
                int.TryParse(input.Substring(colon + 1), out secs))
                ms = (mins * 60 + secs) * 1000;
        }
        else
        {
            int num;
            if (int.TryParse(input, out num))
                ms = num < 1000 ? num * 1000 : num;
        }

        if (ms <= 0)
        {
            CPH.SendMessage("Invalid seek position. Usage: !seek <seconds> or !seek <mm:ss>");
            return false;
        }

        string json = "{\"type\":\"playbackControl\",\"command\":\"seek\",\"position\":" + ms + "}";
        CPH.WebsocketSend(json, 0);
        CPH.SendMessage($"⏩ Seeked to {input}");
        return true;
    }
}
