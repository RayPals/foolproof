using Microsoft.UI.Xaml;
using System.Text.Json;
using System.Text;

namespace Foolproof.Native;

public partial class App : Application
{
    private Window? window;
    private static readonly StringBuilder resourceErrors = new();
    public App()
    {
        UnhandledException += (_, args) => ReportStartupError(args.Exception, args.Message);
        DebugSettings.IsXamlResourceReferenceTracingEnabled = true;
        DebugSettings.XamlResourceReferenceFailed += (_, args) => resourceErrors.AppendLine(args.Message);
        try { InitializeComponent(); }
        catch (Exception ex) { ReportStartupError(ex, ex.Message); throw; }
    }
    protected override void OnLaunched(LaunchActivatedEventArgs args)
    {
        try
        {
            window = new MainWindow();
            window.Activate();
        }
        catch (Exception ex)
        {
            ReportStartupError(ex, ex.Message);
            Environment.Exit(1);
        }
    }

    private static void ReportStartupError(Exception exception, string message)
    {
        try
        {
            var args = Environment.GetCommandLineArgs();
            var index = Array.IndexOf(args, "--smoke-test");
            var folder = index >= 0 && index + 1 < args.Length ? Path.GetFullPath(args[index + 1]) :
                Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Foolproof", "logs");
            Directory.CreateDirectory(folder);
            var details = new StringBuilder(message + Environment.NewLine + exception);
            for (Exception? current = exception; current is not null; current = current.InnerException)
            {
                details.AppendLine($"\nHRESULT: 0x{current.HResult:X8}");
                foreach (System.Collections.DictionaryEntry item in current.Data)
                    if (item.Value is string value) details.AppendLine($"{item.Key}: {value}");
            }
            File.WriteAllText(Path.Combine(folder, "startup-error.txt"), details.ToString());
            File.WriteAllText(Path.Combine(folder, "xaml-resources.txt"), resourceErrors.ToString());
            if (index >= 0)
                File.WriteAllText(Path.Combine(folder, "smoke-result.json"), JsonSerializer.Serialize(new { success = false, checks = 0, error = exception.ToString(), message, realMaintenanceExecuted = false }));
        }
        catch (Exception) { /* Do not mask the original startup exception. */ }
    }
}
