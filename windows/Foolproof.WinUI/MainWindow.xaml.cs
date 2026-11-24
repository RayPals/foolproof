using System.ComponentModel;
using System.Diagnostics;
using System.Runtime.InteropServices.WindowsRuntime;
using System.Security.Principal;
using System.Text;
using System.Text.Json;
using Microsoft.UI;
using Microsoft.UI.Windowing;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using Microsoft.UI.Xaml.Media.Imaging;
using Windows.Graphics;
using Windows.Graphics.Imaging;
using Windows.Storage;

namespace Foolproof.Native;

public sealed partial class MainWindow : Window
{
    private Process? worker;
    private bool busy;
    private bool closePending;
    private bool cancelling;
    private Task? currentRun;
    private readonly StringBuilder log = new();
    private readonly string? smokeDirectory;
    private readonly Dictionary<string, TextBlock> taskLabels;
    private bool completeReceived;
    private bool lastPreview;
    private bool lastCancelled;
    private int lastFailed;
    private int lastSkipped;
    private int plannedTasks;
    private int checks;
    private static string LogFolder => Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Foolproof", "logs");

    public MainWindow()
    {
        var args = Environment.GetCommandLineArgs();
        var smokeIndex = Array.IndexOf(args, "--smoke-test");
        if (smokeIndex >= 0 && smokeIndex + 1 < args.Length)
            smokeDirectory = Path.GetFullPath(args[smokeIndex + 1]);
        InitializeComponent();
        SystemBackdrop = new MicaBackdrop();
        AppWindow.Resize(new SizeInt32(760, 900));
        var icon = Path.Combine(AppContext.BaseDirectory, "Assets", "foolproof-logo.ico");
        if (File.Exists(icon)) AppWindow.SetIcon(icon);
        taskLabels = new()
        {
            ["Check Windows updates"] = UpdateStatus,
            ["Optimize system drive"] = DriveStatus,
            ["Run Disk Cleanup"] = CleanupStatus,
            ["Run antivirus scan"] = ScanStatus
        };
        AdminText.Text = IsAdministrator() ? "Administrator mode is on." : "Administrator access is needed for drive care, cleanup and scanning.";
        AdminButton.Visibility = IsAdministrator() ? Visibility.Collapsed : Visibility.Visible;
        AppWindow.Closing += OnClosing;
        if (smokeDirectory is not null) Root.Loaded += Smoke_Loaded;
    }

    private static bool IsAdministrator()
    {
        using var identity = WindowsIdentity.GetCurrent();
        return new WindowsPrincipal(identity).IsInRole(WindowsBuiltInRole.Administrator);
    }

    private void Preview_Toggled(object sender, RoutedEventArgs e)
    {
        // XAML can fire Toggled before later named elements are constructed.
        if (StartButton is null || PreviewDescription is null) return;
        StartButton.Content = PreviewToggle.IsOn ? "Preview maintenance" : "Start maintenance";
        PreviewDescription.Text = PreviewToggle.IsOn ? "See the steps without changing your PC." : "Maintenance will make changes to your PC.";
        ResultText.Text = PreviewToggle.IsOn ? "You're in control. No changes in preview mode." : "You'll confirm before any maintenance starts.";
    }

    private void FullScan_Changed(object sender, RoutedEventArgs e)
    {
        if (ScanDescription is not null)
            ScanDescription.Text = (sender as CheckBox)?.IsChecked == true ? "A full Defender scan. This can take a few hours." : "A quick check with Microsoft Defender.";
    }

    private async void Start_Click(object sender, RoutedEventArgs e)
    {
        if (busy) return;
        if (!PreviewToggle.IsOn)
        {
            var dialog = new ContentDialog
            {
                XamlRoot = Root.XamlRoot,
                Title = "Start maintenance?",
                Content = "Windows will optimize your system drive, remove temporary files with Disk Cleanup, and run Microsoft Defender. Windows updates are checked, not installed. " +
                    (IsAdministrator() ? "" : "You are not running as administrator, so privileged tasks will be skipped."),
                PrimaryButtonText = "Start maintenance",
                CloseButtonText = "Not now",
                DefaultButton = ContentDialogButton.Close
            };
            if (await dialog.ShowAsync() != ContentDialogResult.Primary) return;
        }
        currentRun = RunAsync();
        await currentRun;
    }

    private void SetBusy(bool value)
    {
        busy = value;
        StartButton.IsEnabled = !value;
        OptionsExpander.IsEnabled = !value;
        PreviewToggle.IsEnabled = !value;
        CancelButton.Visibility = value ? Visibility.Visible : Visibility.Collapsed;
        CancelButton.IsEnabled = value;
        CancelButton.Content = "Cancel";
        RunProgress.Visibility = value ? Visibility.Visible : Visibility.Collapsed;
        RunProgress.IsIndeterminate = value;
    }

    private async Task RunAsync()
    {
        if (busy) return;
        bool preview = PreviewToggle.IsOn;
        SetBusy(true);
        cancelling = false;
        completeReceived = false;
        lastFailed = lastSkipped = plannedTasks = 0;
        lastCancelled = false;
        log.Clear();
        LogText.Text = "";
        foreach (var label in taskLabels.Values) label.Text = "Waiting";
        Headline.Text = preview ? "Let's take a look." : "Taking care of your PC.";
        Summary.Text = preview ? "Reviewing the steps. Nothing will be changed." : "This may take a while. You can cancel at any time.";
        ResultText.Text = "Starting…";
        try
        {
            // Smoke tests can never launch maintenance, even if a test changes a toggle.
            if (smokeDirectory is not null && !preview) throw new InvalidOperationException("Smoke tests are preview-only.");
            var executable = Path.Combine(AppContext.BaseDirectory, "backend", "Foolproof.Worker.exe");
            if (!File.Exists(executable)) throw new FileNotFoundException("The maintenance engine is missing. Extract the entire ZIP before opening Foolproof.");
            var start = new ProcessStartInfo(executable)
            {
                UseShellExecute = false, CreateNoWindow = true,
                RedirectStandardOutput = true, RedirectStandardError = true, RedirectStandardInput = true,
                StandardOutputEncoding = Encoding.UTF8, StandardErrorEncoding = Encoding.UTF8,
                WorkingDirectory = AppContext.BaseDirectory
            };
            if (!preview) start.ArgumentList.Add("--execute");
            if (UpdatesCheck.IsChecked != true) start.ArgumentList.Add("--no-updates");
            if (FullScanCheck.IsChecked == true) start.ArgumentList.Add("--full-scan");
            if (smokeDirectory is not null)
            {
                start.ArgumentList.Add("--log-path");
                start.ArgumentList.Add(Path.Combine(smokeDirectory, "maintenance-preview.log"));
            }
            worker = Process.Start(start) ?? throw new IOException("The maintenance engine could not start.");
            var errorRead = worker.StandardError.ReadToEndAsync();
            while (await worker.StandardOutput.ReadLineAsync() is { } line)
                HandleEvent(line);
            await worker.WaitForExitAsync();
            var error = await errorRead;
            if (!string.IsNullOrWhiteSpace(error)) AddLog(error.Trim());
            if (!completeReceived)
                throw new IOException(cancelling ? "The engine was stopped after cancellation." : $"The maintenance engine ended unexpectedly (code {worker.ExitCode}).");
            Headline.Text = lastCancelled ? "Maintenance stopped." : lastFailed > 0 ? "Some steps need attention." : preview ? "Preview complete." : "All finished.";
            Summary.Text = lastCancelled ? "No more steps will run." : lastFailed > 0 ? "Open the activity log to see what happened." : preview ? "No changes were made to your PC." : lastSkipped > 0 ? "Some steps were skipped. The activity log has the details." : "Your maintenance run has finished.";
            ResultText.Text = lastFailed > 0 ? $"{lastFailed} step(s) reported a problem." : lastSkipped > 0 ? $"{lastSkipped} step(s) skipped. Try administrator mode for privileged tasks." : lastCancelled ? "Cancellation is best-effort; Windows may continue background work." : preview ? "Turn off Preview only when you're ready to make changes." : "You can close Foolproof now.";
        }
        catch (Exception ex)
        {
            if (worker is { HasExited: false })
            {
                try { worker.Kill(entireProcessTree: true); await worker.WaitForExitAsync(); }
                catch (InvalidOperationException) { }
                catch (Win32Exception) { }
            }
            lastFailed = Math.Max(1, lastFailed);
            Headline.Text = cancelling ? "Maintenance stopped." : "Couldn't finish this run.";
            Summary.Text = ex.Message;
            ResultText.Text = "Open the activity log for details.";
            AddLog(ex.Message);
            DetailsExpander.IsExpanded = true;
        }
        finally
        {
            worker?.Dispose();
            worker = null;
            SetBusy(false);
            if (closePending) Close();
        }
    }

    private void HandleEvent(string line)
    {
        using var document = JsonDocument.Parse(line);
        var root = document.RootElement;
        switch (root.GetProperty("type").GetString())
        {
            case "log": AddLog(root.GetProperty("message").GetString() ?? ""); break;
            case "plan":
                plannedTasks = root.GetProperty("tasks").GetArrayLength();
                foreach (var label in taskLabels.Values) label.Text = "Off";
                foreach (var task in root.GetProperty("tasks").EnumerateArray())
                    if (taskLabels.TryGetValue(task.GetString() ?? "", out var label)) label.Text = "Ready";
                break;
            case "task":
                if (taskLabels.TryGetValue(root.GetProperty("name").GetString() ?? "", out var status))
                    status.Text = root.GetProperty("status").GetString() ?? "";
                break;
            case "complete":
                lastFailed = root.GetProperty("failed").GetInt32();
                lastSkipped = root.GetProperty("skipped").GetInt32();
                lastCancelled = root.GetProperty("cancelled").GetBoolean();
                lastPreview = root.GetProperty("preview").GetBoolean();
                completeReceived = true;
                break;
        }
    }

    private void AddLog(string text)
    {
        log.AppendLine(text);
        LogText.Text = log.ToString(); // Native TextBox displays literal text, never HTML.
    }

    private async void Cancel_Click(object sender, RoutedEventArgs e) => await CancelAsync();
    private async Task CancelAsync()
    {
        if (!busy || cancelling) return;
        cancelling = true;
        CancelButton.IsEnabled = false;
        CancelButton.Content = "Stopping…";
        ResultText.Text = "Stopping the current step before continuing…";
        try
        {
            var process = worker;
            if (process is { HasExited: false })
            {
                await process.StandardInput.WriteLineAsync("cancel");
                await process.StandardInput.FlushAsync();
                // Give the tested engine time to terminate and reap its child.
                var exit = process.WaitForExitAsync();
                if (await Task.WhenAny(exit, Task.Delay(5000)) != exit && worker is { HasExited: false })
                    worker.Kill(entireProcessTree: true);
            }
        }
        catch (IOException) { }
        catch (InvalidOperationException) { } // Includes already-disposed processes.
        catch (Win32Exception ex) { AddLog($"Cancellation could not stop the engine: {ex.Message}"); }
    }

    private async void OnClosing(AppWindow sender, AppWindowClosingEventArgs args)
    {
        if (!busy) return;
        args.Cancel = true;
        closePending = true;
        await CancelAsync();
    }

    private void Admin_Click(object sender, RoutedEventArgs e)
    {
        if (busy || smokeDirectory is not null) return;
        try
        {
            var start = new ProcessStartInfo(Environment.ProcessPath!) { UseShellExecute = true, Verb = "runas", WorkingDirectory = AppContext.BaseDirectory };
            using var elevated = Process.Start(start);
            if (elevated is not null) Close();
        }
        catch (Win32Exception) { ResultText.Text = "Administrator access wasn't granted. No maintenance started."; }
    }

    private void OpenLog_Click(object sender, RoutedEventArgs e)
    {
        try
        {
            Directory.CreateDirectory(LogFolder);
            using var process = Process.Start(new ProcessStartInfo(LogFolder) { UseShellExecute = true });
        }
        catch (Exception ex) { ResultText.Text = $"Couldn't open the log folder: {ex.Message}"; }
    }

    private void Check(bool condition, string name)
    {
        if (!condition) throw new InvalidOperationException("Smoke assertion failed: " + name);
        checks++;
    }

    private async void Smoke_Loaded(object sender, RoutedEventArgs e)
    {
        Root.Loaded -= Smoke_Loaded;
        Directory.CreateDirectory(smokeDirectory!);
        try
        {
            await Task.Delay(1000);
            Check(PreviewToggle.IsOn, "Preview is on by default");
            Check(!OptionsExpander.IsExpanded && !DetailsExpander.IsExpanded, "Advanced panels start collapsed");
            Check(CancelButton.Visibility == Visibility.Collapsed && StartButton.IsEnabled, "Idle controls");
            Check(LogText.IsReadOnly, "Log is read-only");
            Check((string)StartButton.Content == "Preview maintenance", "Clear primary preview action");
            foreach (var element in new FrameworkElement[] { PageContent, StartButton, UpdateStatus, DriveStatus, CleanupStatus, ScanStatus })
            {
                var position = element.TransformToVisual(Root).TransformPoint(new Windows.Foundation.Point(0, 0));
                Check(position.X >= -1 && position.X + element.ActualWidth <= Root.ActualWidth + 1, "No horizontal clipping: " + element.Name);
            }
            await SnapshotAsync("ready.png");
            currentRun = RunAsync();
            Check(!OptionsExpander.IsEnabled && !PreviewToggle.IsEnabled && !StartButton.IsEnabled, "Options stay disabled during a run");
            await currentRun;
            Check(completeReceived && lastPreview && lastFailed == 0, "Real bundled worker preview succeeds");
            Check(plannedTasks == 4 && taskLabels.Values.All(label => label.Text == "Previewed"), "Four task statuses reach previewed");
            Check(StartButton.IsEnabled && !busy && CancelButton.Visibility == Visibility.Collapsed, "Controls recover");
            Check(LogText.Text.Contains("DRY RUN: powershell") && LogText.Text.Contains("MpCmdRun.exe\""), "Literal command quotes reach native log");
            Check(!LogText.Text.Contains("&quot;") && !LogText.Text.Contains("&#x27;"), "No introduced HTML entities");
            await SnapshotAsync("preview-complete.png");
            OptionsExpander.IsExpanded = true;
            UpdatesCheck.IsChecked = false;
            FullScanCheck.IsChecked = true;
            currentRun = RunAsync();
            await currentRun;
            Check(completeReceived && lastPreview && lastFailed == 0 && plannedTasks == 3, "Settings alter the worker plan");
            Check(LogText.Text.Contains("-ScanType 2") && UpdateStatus.Text == "Off", "Full scan and disabled update option are wired");
            PreviewToggle.IsOn = false;
            Check((string)StartButton.Content == "Start maintenance", "Live mode is clearly labelled");
            PreviewToggle.IsOn = true;
            Check((string)StartButton.Content == "Preview maintenance", "Preview label restores");
            File.WriteAllText(Path.Combine(smokeDirectory!, "smoke-result.json"), JsonSerializer.Serialize(new { success = true, checks, realMaintenanceExecuted = false, framework = "WinUI 3" }));
        }
        catch (Exception ex)
        {
            File.WriteAllText(Path.Combine(smokeDirectory!, "smoke-result.json"), JsonSerializer.Serialize(new { success = false, checks, error = ex.ToString(), realMaintenanceExecuted = false }));
            Environment.ExitCode = 1;
        }
        Application.Current.Exit();
    }

    private async Task SnapshotAsync(string name)
    {
        await Task.Delay(300);
        var bitmap = new RenderTargetBitmap();
        await bitmap.RenderAsync(Root);
        var pixels = await bitmap.GetPixelsAsync();
        Check(bitmap.PixelWidth > 0 && bitmap.PixelHeight > 0 && pixels.Length > 0, "Rendered " + name);
        var folder = await StorageFolder.GetFolderFromPathAsync(smokeDirectory!);
        var file = await folder.CreateFileAsync(name, CreationCollisionOption.ReplaceExisting);
        using var stream = await file.OpenAsync(FileAccessMode.ReadWrite);
        var encoder = await BitmapEncoder.CreateAsync(BitmapEncoder.PngEncoderId, stream);
        encoder.SetPixelData(BitmapPixelFormat.Bgra8, BitmapAlphaMode.Premultiplied, (uint)bitmap.PixelWidth, (uint)bitmap.PixelHeight, 96, 96, pixels.ToArray());
        await encoder.FlushAsync();
    }
}
