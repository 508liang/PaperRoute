// Copyright (C) 2026 PaperRoute contributors. AGPL-3.0-only.
// Offline single-file distribution. The runtime is expanded once and reused.
using System;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.IO.Compression;
using System.Reflection;
using System.Text;
using System.Threading;
using System.Windows.Forms;

[assembly: AssemblyTitle("PaperRoute")]
[assembly: AssemblyDescription("PaperRoute - 选路译读 / self-contained Windows edition")]
[assembly: AssemblyProduct("PaperRoute")]
[assembly: AssemblyCompany("PaperRoute contributors")]
[assembly: AssemblyCopyright("Copyright (C) 2026 PaperRoute contributors")]
[assembly: AssemblyVersion("0.1.0.0")]
[assembly: AssemblyFileVersion("0.1.0.0")]
[assembly: System.Runtime.Versioning.TargetFramework(".NETFramework,Version=v4.7.2")]

internal static partial class PaperRouteSingleFile
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

    private static bool Ready(string root)
    {
        return File.Exists(Path.Combine(root, ".ready")) &&
            File.ReadAllText(Path.Combine(root, ".ready")) == PayloadId &&
            File.Exists(Path.Combine(root, "core", "runtime", "pythonw.exe")) &&
            File.Exists(Path.Combine(root, "_launcher.py")) &&
            File.Exists(Path.Combine(root, "assets", "doclayout_yolo.onnx"));
    }

    private static string ExpandRuntime(string data)
    {
        string runtimeBase = Path.Combine(data, "runtime");
        string root = Path.Combine(runtimeBase, PayloadId);
        if (Ready(root)) return root;
        Directory.CreateDirectory(runtimeBase);
        using (var progress = new Form())
        using (var mutex = new Mutex(false, "Local\\PaperRoute-Expand-" + PayloadId))
        {
            progress.Text = "PaperRoute · 选路译读";
            progress.ClientSize = new Size(430, 118);
            progress.FormBorderStyle = FormBorderStyle.FixedDialog;
            progress.StartPosition = FormStartPosition.CenterScreen;
            progress.MaximizeBox = false;
            progress.MinimizeBox = false;
            progress.ControlBox = false;
            progress.BackColor = Color.FromArgb(243, 246, 250);
            var label = new Label { Left = 22, Top = 20, Width = 390, Height = 44,
                Text = "首次启动，正在准备运行环境…\n准备完成后会自动打开，以后无需重复展开。" };
            var bar = new ProgressBar { Left = 22, Top = 78, Width = 386, Height = 12, Maximum = 100 };
            progress.Controls.Add(label);
            progress.Controls.Add(bar);
            progress.Show();
            Application.DoEvents();
            bool locked = false;
            string pending = null;
            try
            {
                var deadline = DateTime.UtcNow.AddMinutes(2);
                while (!locked)
                {
                    try { locked = mutex.WaitOne(100); }
                    catch (AbandonedMutexException) { locked = true; }
                    Application.DoEvents();
                    if (!locked && DateTime.UtcNow > deadline) throw new IOException("另一个启动进程仍在准备运行环境，请稍后重试。");
                }
                if (Ready(root)) return root;
                pending = Path.Combine(runtimeBase, ".new-" + Guid.NewGuid().ToString("N").Substring(0, 12));
                Directory.CreateDirectory(pending);
                string prefix = Path.GetFullPath(pending) + Path.DirectorySeparatorChar;
                using (Stream resource = Assembly.GetExecutingAssembly().GetManifestResourceStream("PaperRoute.Payload.zip"))
                {
                    if (resource == null) throw new IOException("内置运行环境缺失，请重新获取完整的 exe。");
                    using (var archive = new ZipArchive(resource, ZipArchiveMode.Read))
                    {
                        long total = 0, written = 0;
                        foreach (var entry in archive.Entries) total += entry.Length;
                        byte[] buffer = new byte[1024 * 1024];
                        foreach (var entry in archive.Entries)
                        {
                            string target = Path.GetFullPath(Path.Combine(pending, entry.FullName.Replace('/', Path.DirectorySeparatorChar)));
                            if (!target.StartsWith(prefix, StringComparison.OrdinalIgnoreCase)) throw new IOException("运行环境中有无效路径。");
                            if (String.IsNullOrEmpty(entry.Name)) { Directory.CreateDirectory(target); continue; }
                            Directory.CreateDirectory(Path.GetDirectoryName(target));
                            using (Stream source = entry.Open())
                            using (var output = new FileStream(target, FileMode.CreateNew, FileAccess.Write, FileShare.None))
                            {
                                int count;
                                while ((count = source.Read(buffer, 0, buffer.Length)) > 0)
                                {
                                    output.Write(buffer, 0, count);
                                    written += count;
                                    int value = total > 0 ? (int)(written * 100 / total) : 0;
                                    if (value != bar.Value) { bar.Value = value; Application.DoEvents(); }
                                }
                            }
                        }
                    }
                }
                File.WriteAllText(Path.Combine(pending, ".ready"), PayloadId);
                if (Directory.Exists(root))
                    Directory.Move(root, root + ".incomplete-" + Guid.NewGuid().ToString("N"));
                Directory.Move(pending, root);
                pending = null;
                return root;
            }
            finally
            {
                if (locked) mutex.ReleaseMutex();
                // Only remove the staging folder created by this invocation.
                if (pending != null && Path.GetFullPath(pending).StartsWith(Path.GetFullPath(runtimeBase) + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase))
                {
                    try { Directory.Delete(pending, true); } catch (IOException) { }
                }
                progress.Close();
            }
        }
    }

    private static void ImportAdjacentConfiguration(string data)
    {
        // Never embed personal data. Existing settings may be copied at run time
        // when this exe is placed beside a full portable install.
        if (Environment.GetEnvironmentVariable("PAPERROUTE_NO_MIGRATION") == "1") return;
        string adjacent = AppDomain.CurrentDomain.BaseDirectory;
        if (!File.Exists(Path.Combine(adjacent, "_launcher.py")))
        {
            var parent = Directory.GetParent(adjacent.TrimEnd(Path.DirectorySeparatorChar));
            if (parent == null || !File.Exists(Path.Combine(parent.FullName, "_launcher.py")) ||
                !File.Exists(Path.Combine(parent.FullName, "core", "runtime", "pythonw.exe"))) return;
            adjacent = parent.FullName;
        }
        string destination = Path.Combine(data, "config");
        Directory.CreateDirectory(destination);
        foreach (string name in new[] { "local_models.json", "local_gui_config.json", "local_engine_config.json", "local_history.json" })
        {
            string source = Path.Combine(adjacent, "config", name);
            string target = Path.Combine(destination, name);
            if (File.Exists(source) && !File.Exists(target)) File.Copy(source, target);
        }
    }

    [STAThread]
    private static int Main(string[] arguments)
    {
        AppContext.SetSwitch("Switch.System.IO.UseLegacyPathHandling", false);
        AppContext.SetSwitch("Switch.System.IO.BlockLongPaths", false);
        Application.EnableVisualStyles();
        Application.SetCompatibleTextRenderingDefault(false);
        try
        {
            string data = Environment.GetEnvironmentVariable("PAPERROUTE_DATA_DIR");
            if (String.IsNullOrWhiteSpace(data)) data = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "PaperRoute");
            data = Path.GetFullPath(data);
            Directory.CreateDirectory(data);
            string root = ExpandRuntime(data);
            ImportAdjacentConfiguration(data);
            var command = new StringBuilder(Quote(Path.Combine(root, "_launcher.py")));
            foreach (string argument in arguments) command.Append(' ').Append(Quote(argument));
            var info = new ProcessStartInfo(Path.Combine(root, "core", "runtime", "pythonw.exe"), command.ToString());
            info.WorkingDirectory = data;
            info.UseShellExecute = false;
            info.CreateNoWindow = true;
            info.EnvironmentVariables.Remove("PYTHONHOME");
            info.EnvironmentVariables.Remove("PYTHONPATH");
            info.EnvironmentVariables["PYTHONDONTWRITEBYTECODE"] = "1";
            info.EnvironmentVariables["PYTHONIOENCODING"] = "utf-8";
            info.EnvironmentVariables["PAPERROUTE_DATA_DIR"] = data;
            info.EnvironmentVariables["PAPERROUTE_NO_LEGACY_IMPORT"] = "1";
            info.EnvironmentVariables["PDF2ZH_CACHE_DIR"] = Path.Combine(data, "cache");
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
