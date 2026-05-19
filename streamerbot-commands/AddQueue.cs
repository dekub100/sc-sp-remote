using System;

public class CPHInline
{
    public bool Execute()
    {
        string input = args["rawInput"].ToString();
        if (string.IsNullOrWhiteSpace(input))
        {
            CPH.SendMessage("Please provide a Spotify track URL or URI.");
            return false;
        }

        string json = $"{{\"type\":\"addToQueue\",\"input\":\"{input.Replace("\"", "\\\"")}\",\"requestedBy\":\"streamer.bot\"}}";
        CPH.WebsocketSend(json, 0);
        CPH.SendMessage($"🎵 Added to queue!");
        CPH.LogInfo($"AddQueue: Added '{input}'");
        return true;
    }
}
