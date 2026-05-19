using System;

public class CPHInline
{
    public bool Execute()
    {
        CPH.WebsocketSend("{\"type\":\"playbackControl\",\"command\":\"previous\"}", 0);
        CPH.SendMessage("⏮️ Went to previous track");
        return true;
    }
}
