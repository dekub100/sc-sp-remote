using System;

public class CPHInline
{
    public bool Execute()
    {
        // Usage:
        //   !seek 1:30   → 1 minute 30 seconds
        //   !seek 90     → 90 seconds
        //   !seek 45000  → 45000 ms (raw, for power users)
        // Maps to %position% in command settings
        object posObj;
        if (!CPH.TryGetArg("position", out posObj) && !CPH.TryGetArg("rawInput", out posObj))
            return false;

        string input = posObj.ToString().Trim();
        int ms = 0;

        // Try mm:ss format
        int colon = input.IndexOf(':');
        if (colon > 0)
        {
            int mins, secs;
            if (int.TryParse(input.Substring(0, colon), out mins) &&
                int.TryParse(input.Substring(colon + 1), out secs))
                ms = (mins * 60 + secs) * 1000;
        }
        // Try number — treat as seconds if < 1000, otherwise ms
        else
        {
            int num;
            if (int.TryParse(input, out num))
                ms = num < 1000 ? num * 1000 : num;
        }

        if (ms <= 0)
            return false;

        string json = "{\"type\":\"playbackControl\",\"command\":\"seek\",\"position\":" + ms + "}";
        CPH.WebsocketSend(json, 0);
        return true;
    }
}
