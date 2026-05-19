using System;

public class CPHInline
{
    public bool Execute()
    {
        CPH.WebsocketSend("{\"type\":\"playbackControl\",\"command\":\"toggleShuffle\"}", 0);
        CPH.SendMessage("🔀 Toggled shuffle");
        return true;
    }
}
