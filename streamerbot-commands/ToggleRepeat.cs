using System;

public class CPHInline
{
    public bool Execute()
    {
        CPH.WebsocketSend("{\"type\":\"playbackControl\",\"command\":\"toggleRepeat\"}", 0);
        return true;
    }
}
