using System;
using System.Diagnostics;
using System.IO;
using System.Threading;

namespace SemanticBridgeNativeMessaging
{
    // Fixed binary-stdio relay, no network endpoint and no shell execution.
    // Chrome requires a real .exe native host on Windows (not .cmd).
    public static class Proxy
    {
        public static int Main(string[] args)
        {
            Process child = null;
            try
            {
                string configPath = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "native_host_paths.txt");
                string[] paths = File.ReadAllLines(configPath);
                if (paths.Length != 2 || !Path.IsPathRooted(paths[0]) ||
                    !Path.IsPathRooted(paths[1]) || !File.Exists(paths[0]) ||
                    !File.Exists(paths[1])) return 7;
                var start = new ProcessStartInfo();
                start.FileName = paths[0];
                start.Arguments = "-u \"" + paths[1].Replace("\"", "") + "\"";
                start.UseShellExecute = false;
                start.CreateNoWindow = true;
                start.RedirectStandardInput = true;
                start.RedirectStandardOutput = true;
                start.RedirectStandardError = false;
                child = new Process();
                child.StartInfo = start;
                if (!child.Start()) return 8;

                Process proc = child;
                Thread incoming = new Thread(delegate() {
                    try
                    {
                        Stream incomingStream = Console.OpenStandardInput(1);
                        byte[] buffer = new byte[512];
                        int received;
                        while ((received = incomingStream.Read(buffer,0,buffer.Length)) > 0)
                        {
                            proc.StandardInput.BaseStream.Write(buffer,0,received);
                            proc.StandardInput.BaseStream.Flush();
                        }
                    }
                    catch (IOException) {}
                    catch (ObjectDisposedException) {}
                    finally
                    {
                        try { proc.StandardInput.Close(); } catch (Exception) {}
                    }
                });
                incoming.IsBackground = true;
                incoming.Start();

                // This thread owns stdout and copies raw little-endian frames.
                // Never use Console.Write/WriteLine (which would corrupt frames).
                Stream output = Console.OpenStandardOutput();
                proc.StandardOutput.BaseStream.CopyTo(output);
                output.Flush();

                if (!proc.WaitForExit(2000))
                {
                    proc.Kill();
                    proc.WaitForExit(2000);
                }
                return proc.ExitCode;
            }
            catch (Exception)
            {
                if (child != null)
                {
                    try { if (!child.HasExited) child.Kill(); }
                    catch (Exception) {}
                }
                return 9;
            }
            finally
            {
                if (child != null) child.Dispose();
            }
        }
    }
}