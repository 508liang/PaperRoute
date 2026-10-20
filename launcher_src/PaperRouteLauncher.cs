// Copyright (C) 2026 PaperRoute contributors. AGPL-3.0-only.
using System;
using System.Diagnostics;
using System.IO;
using System.Reflection;
using System.Text;
using System.Windows.Forms;

[assembly: AssemblyTitle("PaperRoute")]
[assembly: AssemblyDescription("PaperRoute - 选路译读 / PDF translation desktop launcher")]
[assembly: AssemblyProduct("PaperRoute")]
[assembly: AssemblyCompany("PaperRoute contributors")]
[assembly: AssemblyCopyright("Copyright (C) 2026 PaperRoute contributors")]
[assembly: AssemblyVersion("0.1.0.0")]
[assembly: AssemblyFileVersion("0.1.0.0")]

internal static class PaperRouteLauncher
{
    private static string Quote(string value)
    {
        var result = new StringBuilder("\"");
        int slashes = 0;
        foreach (char character in value)
        {
            if (character == '\\') { slashes++; continue; }
            if (character == '"') result.Append('\\', slashes * 2 + 1).Append('"');
            else result.Append('\\', slashes).Append(character);
            slashes = 0;
        }
        return result.Append('\\', slashes * 2).Append('"').ToString();
    }

    [STAThread]
    private static int Main(string[] arguments)
    {
        string root = AppDomain.CurrentDomain.BaseDirectory;
        string python = Path.Combine(root, "core", "runtime", "pythonw.exe");
        string script = Path.Combine(root, "_launcher.py");
        if (!File.Exists(python) || !File.Exists(script))
        {
            MessageBox.Show("请解压完整的 PaperRoute 文件夹，再运行程序。\n运行时或启动脚本缺失。", "PaperRoute", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
        }
        try
        {
            var text = new StringBuilder(Quote(script));
            foreach (string argument in arguments) text.Append(' ').Append(Quote(argument));
            var info = new ProcessStartInfo(python, text.ToString());
            info.WorkingDirectory = root;
            info.UseShellExecute = false;
            info.CreateNoWindow = true;
            info.EnvironmentVariables.Remove("PYTHONHOME");
            info.EnvironmentVariables.Remove("PYTHONPATH");
            info.EnvironmentVariables["PYTHONDONTWRITEBYTECODE"] = "1";
            info.EnvironmentVariables["PYTHONIOENCODING"] = "utf-8";
            Process.Start(info);
            return 0;
        }
        catch (Exception error)
        {
            MessageBox.Show("启动失败：" + error.Message, "PaperRoute", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
        }
    }
}
