using System;

public class CPHInline
{
    public bool Execute()
    {
        CPH.WebsocketSend("{\"type\":\"playbackControl\",\"command\":\"next\"}", 0);
        CPH.SendMessage("⏭️ Skipped to next track");
        return true;
    }
}
