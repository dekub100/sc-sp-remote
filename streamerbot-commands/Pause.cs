using System;

public class CPHInline
{
    public bool Execute()
    {
        CPH.WebsocketSend("{\"type\":\"playbackControl\",\"command\":\"pause\"}", 0);
        return true;
    }
}
