"""Structural guardrails; the Windows build also runs real WinUI smoke tests."""
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT / 'windows' / 'Foolproof.WinUI'
XAML = {'x': 'http://schemas.microsoft.com/winfx/2006/xaml'}


def test_native_ui_uses_winui_and_bundles_its_runtime():
    project = NATIVE / 'Foolproof.WinUI.csproj'
    assert project.exists(), 'Native WinUI project must exist'
    root = ET.parse(project).getroot()
    assert root.findtext('.//UseWinUI') == 'true'
    assert root.findtext('.//WindowsAppSDKSelfContained') == 'true'
    assert root.findtext('.//SelfContained') == 'true'
    assert root.findtext('.//WindowsPackageType') == 'None'
    tools = root.find(".//PackageReference[@Include='Microsoft.Windows.SDK.BuildTools']")
    if tools is not None:
        assert tuple(map(int, tools.get('Version').split('.'))) >= (10, 0, 26100, 4654)


def test_native_publish_includes_the_application_resource_index():
    root = ET.parse(NATIVE / 'Foolproof.WinUI.csproj').getroot()
    target = root.find(".//Target[@Name='PublishAppResourceIndex']")
    assert target is not None, 'Unpackaged publish must explicitly include its app PRI (WindowsAppSDK #6720)'
    item = target.find('.//ResolvedFileToPublish')
    assert item is not None and item.get('Include') == '$(ProjectPriFullPath)'
    assert item.findtext('RelativePath') == '$(ProjectPriFileName)'


def test_native_ui_keeps_preview_default_and_hides_advanced_controls():
    file = NATIVE / 'MainWindow.xaml'
    assert file.exists(), 'Native main screen must exist'
    root = ET.parse(file).getroot()
    scroll = next(e for e in root.iter() if e.tag.endswith('ScrollViewer'))
    assert scroll.get('HorizontalContentAlignment') == 'Stretch'
    assert scroll.get('HorizontalScrollMode') == 'Disabled'
    named = {e.get('{'+XAML['x']+'}Name'): e for e in root.iter()}
    assert named['PreviewToggle'].get('IsOn') == 'True'
    assert named['OptionsExpander'].get('IsExpanded') == 'False'
    assert named['DetailsExpander'].get('IsExpanded') == 'False'
    assert named['CancelButton'].get('Visibility') == 'Collapsed'
    assert named['LogText'].get('IsReadOnly') == 'True'
    assert named['StartButton'].get('Click') == 'Start_Click'
