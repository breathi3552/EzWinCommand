"""电竞模式插件。"""
from __future__ import annotations
import os
import subprocess
import time
from typing import Any

import psutil
import config
from plugins.base import BasePlugin, CommandResult

YY_PROCESS_NAMES = {"yy.exe"}


def _yy_uri_handler_available() -> bool:
    """检测 Windows 注册表中的 YY URI handler 及其可执行文件。"""
    try:
        import re
        import winreg
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, "yy") as key:
            protocol, _ = winreg.QueryValueEx(key, "URL Protocol")
            if protocol is None:
                return False
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, r"yy\shell\open\command") as key:
            command, _ = winreg.QueryValueEx(key, "")
        command = str(command).strip()
        if "%1" not in command:
            return False
        match = re.match(r'^\s*"([^"]+\.exe)"|^\s*([^\s]+\.exe)', command, re.IGNORECASE)
        exe = (match.group(1) or match.group(2)) if match else ""
        return bool(exe and os.path.isfile(os.path.expandvars(exe)))
    except (ImportError, OSError, FileNotFoundError):
        return False

def _build_yy_join_uri(room_id: str) -> str:
    """构造已验证的 YY 进房 URI。"""
    if not isinstance(room_id, str) or not room_id or not room_id.isdigit():
        raise ValueError("YY_ROOM_ID 必须为纯数字")
    return f"yy://join:room_id={room_id}&sub_room_id={room_id}/"


def _yy_process_exists() -> bool:
    for proc in psutil.process_iter(["name"]):
        try:
            if (proc.info.get("name") or "").lower() in YY_PROCESS_NAMES:
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return False


def _wait_for_yy_ready(timeout_s: float = 15.0, poll_s: float = 0.1) -> bool:
    """等待 URI handler 启动 YY 进程。"""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if _yy_process_exists():
            return True
        time.sleep(poll_s)
    return False


def _submit_yy_join_uri(room_id: str) -> tuple[bool, str]:
    try:
        uri = _build_yy_join_uri(room_id)
    except ValueError as exc:
        return False, str(exc)
    if not _yy_uri_handler_available():
        return False, "yy://未注册或handler无效"
    existed_before = _yy_process_exists()
    try:
        os.startfile(uri)
    except Exception as exc:
        return False, f"YY 启动失败: {exc}"
    if not existed_before and not _wait_for_yy_ready():
        return False, "YY 进程启动超时"
    time.sleep(0.3)
    return True, "YY已发起进房"

def _set_default_audio_device(device_name: str) -> tuple[bool, str]:
    script = r'''$cs=@"
using System; using System.Runtime.InteropServices;
public enum EDataFlow{eRender=0,eCapture=1,eAll=2} public enum ERole{eConsole=0,eMultimedia=1,eCommunications=2}
[StructLayout(LayoutKind.Sequential)] public struct PROPERTYKEY{public Guid fmtid;public int pid;public PROPERTYKEY(Guid f,int p){fmtid=f;pid=p;}}
[StructLayout(LayoutKind.Explicit, Size=24)] public struct PROPVARIANT{[FieldOffset(0)]public ushort vt;[FieldOffset(2)]public ushort r1;[FieldOffset(4)]public ushort r2;[FieldOffset(6)]public ushort r3;[FieldOffset(8)]public IntPtr pointer;}
[ComImport,Guid("A95664D2-9614-4F35-A746-DE8DB63617E6"),InterfaceType(ComInterfaceType.InterfaceIsIUnknown)] public interface IMMDeviceEnumerator{[PreserveSig]int EnumAudioEndpoints(EDataFlow f,int s,out IMMDeviceCollection c);}
[ComImport,Guid("0BD7A1BE-7A1A-44DB-8397-CC5392387B5E"),InterfaceType(ComInterfaceType.InterfaceIsIUnknown)] public interface IMMDeviceCollection{[PreserveSig]int GetCount(out int n);[PreserveSig]int Item(int i,out IMMDevice d);}
[ComImport,Guid("D666063F-1587-4E43-81F1-B948E807363F"),InterfaceType(ComInterfaceType.InterfaceIsIUnknown)] public interface IMMDevice{[PreserveSig]int Activate(ref Guid i,int c,IntPtr p,out IntPtr o);[PreserveSig]int OpenPropertyStore(int a,out IPropertyStore s);[PreserveSig]int GetId(out IntPtr id);[PreserveSig]int GetState(out int state);}
[ComImport,Guid("886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99"),InterfaceType(ComInterfaceType.InterfaceIsIUnknown)] public interface IPropertyStore{[PreserveSig]int GetCount(out int n);[PreserveSig]int GetAt(int i,out PROPERTYKEY k);[PreserveSig]int GetValue(ref PROPERTYKEY k,out PROPVARIANT v);[PreserveSig]int SetValue(ref PROPERTYKEY k,ref PROPVARIANT v);[PreserveSig]int Commit();}
[ComImport,Guid("F8679F50-850A-41CF-9C72-430F290290C8"),InterfaceType(ComInterfaceType.InterfaceIsIUnknown)] public interface IPolicyConfig{[PreserveSig]int GetMixFormat(string id,IntPtr p);[PreserveSig]int GetDeviceFormat(string id,bool mix,IntPtr p);[PreserveSig]int ResetDeviceFormat(string id);[PreserveSig]int SetDeviceFormat(string id,IntPtr p);[PreserveSig]int GetProcessingPeriod(string id,IntPtr d,IntPtr m);[PreserveSig]int SetProcessingPeriod(string id,IntPtr p);[PreserveSig]int GetShareMode(string id,IntPtr m);[PreserveSig]int SetShareMode(string id,IntPtr m);[PreserveSig]int GetPropertyValue(string id,ref PROPERTYKEY k,ref PROPVARIANT v);[PreserveSig]int SetPropertyValue(string id,ref PROPERTYKEY k,ref PROPVARIANT v);[PreserveSig]int SetDefaultEndpoint([MarshalAs(UnmanagedType.LPWStr)]string id,ERole r);}
public static class CA{[DllImport("ole32.dll",EntryPoint="CoCreateInstance")]static extern int CoCreateInstanceRaw(ref Guid c,IntPtr u,uint x,ref Guid i,out IntPtr o);[DllImport("ole32.dll")]static extern int PropVariantClear(ref PROPVARIANT v);static void H(int h,string op){if(h<0)Marshal.ThrowExceptionForHR(h);}public static void SetDefault(string name){if(String.IsNullOrEmpty(name))throw new ArgumentException("音频设备名为空");IMMDeviceEnumerator e=null;IMMDeviceCollection c=null;IPolicyConfig p=null;try{var cls=new Guid("BCDE0395-E52F-467C-8E3D-C4579291692E");var iid=new Guid("A95664D2-9614-4F35-A746-DE8DB63617E6");IntPtr ep;H(CoCreateInstanceRaw(ref cls,IntPtr.Zero,1,ref iid,out ep),"CoCreateInstance");try{e=(IMMDeviceEnumerator)Marshal.GetObjectForIUnknown(ep);}finally{Marshal.Release(ep);}H(e.EnumAudioEndpoints(EDataFlow.eRender,1,out c),"EnumAudioEndpoints");int n;H(c.GetCount(out n),"GetCount");var k=new PROPERTYKEY(new Guid("A45C254E-DF1C-4EFD-8020-67D146A850E0"),14);for(int i=0;i<n;i++){IMMDevice d=null;IPropertyStore s=null;IntPtr idp=IntPtr.Zero;PROPVARIANT v=new PROPVARIANT();try{H(c.Item(i,out d),"Item");H(d.OpenPropertyStore(0,out s),"OpenPropertyStore");H(s.GetValue(ref k,out v),"GetValue");string f=v.vt==31&&v.pointer!=IntPtr.Zero?Marshal.PtrToStringUni(v.pointer):null;if(String.Equals(f,name,StringComparison.Ordinal)){H(d.GetId(out idp),"GetId");string id=Marshal.PtrToStringUni(idp);var pc=new Guid("870AF99C-171D-4F9E-AF0D-E63DF40C2BC9");var pi=new Guid("F8679F50-850A-41CF-9C72-430F290290C8");IntPtr pp;H(CoCreateInstanceRaw(ref pc,IntPtr.Zero,1,ref pi,out pp),"CoCreateInstance(IPolicyConfig)");try{p=(IPolicyConfig)Marshal.GetObjectForIUnknown(pp);}finally{Marshal.Release(pp);}foreach(ERole r in Enum.GetValues(typeof(ERole)))H(p.SetDefaultEndpoint(id,r),"SetDefaultEndpoint");return;}}finally{try{H(PropVariantClear(ref v),"PropVariantClear");}finally{if(idp!=IntPtr.Zero)Marshal.FreeCoTaskMem(idp);if(s!=null)Marshal.ReleaseComObject(s);if(d!=null)Marshal.ReleaseComObject(d);}}}throw new InvalidOperationException("未找到音频设备: "+name);}finally{if(p!=null)Marshal.ReleaseComObject(p);if(c!=null)Marshal.ReleaseComObject(c);if(e!=null)Marshal.ReleaseComObject(e);}}}
"@
Add-Type -TypeDefinition $cs
$name=[string]$env:EZWIN_AUDIO_DEVICE
try{[CA]::SetDefault($name)}catch{[Console]::Error.WriteLine($_.Exception.ToString());exit 1}
'''
    try:
        result=subprocess.run(["powershell.exe","-NoProfile","-NonInteractive","-ExecutionPolicy","Bypass","-Command",script],capture_output=True,text=True,encoding="mbcs",errors="replace",timeout=15,creationflags=subprocess.CREATE_NO_WINDOW,env={**__import__("os").environ,"EZWIN_AUDIO_DEVICE":device_name})
    except subprocess.TimeoutExpired:return False,"音频切换失败: PowerShell 超时"
    except FileNotFoundError:return False,"音频切换失败: 未找到 PowerShell"
    except Exception as exc:return False,f"音频切换失败: {exc}"
    if result.returncode!=0:return False,f"音频切换失败: {(result.stderr or result.stdout or 'COM 调用失败').strip()}"
    return True,"音频设备已切换"

class EsportsModePlugin(BasePlugin):
    name = "esports_mode"
    label = "电竞模式"
    description = "切换电竞音频并管理 YY 与 CS2"
    def get_sub_actions(self) -> list[dict[str, Any]]:
        return [{"id":"enter","label":"进入电竞模式"},{"id":"exit","label":"退出电竞模式"}]
    def execute(self, params: dict[str, Any]) -> CommandResult:
        action = params.get("sub_action", "enter")
        if action == "enter": return self._enter()
        if action == "exit": return self._exit()
        return CommandResult(False, f"未知操作: {action}")
    @staticmethod
    def _enter() -> CommandResult:
        if not config.YY_ROOM_ID:
            return CommandResult(False, "进入电竞模式失败（YY）: YY_ROOM_ID 未配置")
        if not config.YY_ROOM_ID.isdigit():
            return CommandResult(False, "进入电竞模式失败（YY）: YY_ROOM_ID 格式错误，必须为纯数字")
        if not config.STEAM_PATH:
            return CommandResult(False, "进入电竞模式失败: STEAM_PATH 未配置")
        ok, msg = _set_default_audio_device(config.AUDIO_ENTER_DEVICE)
        if not ok:
            return CommandResult(False, f"进入电竞模式失败（音频）: {msg}")
        ok, msg = _submit_yy_join_uri(config.YY_ROOM_ID)
        if not ok:
            return CommandResult(False, f"进入电竞模式失败（YY）: {msg}")
        try:
            subprocess.Popen([config.STEAM_PATH, "-applaunch", "730", "-perfectworld"])
        except Exception as exc:
            return CommandResult(False, f"YY已发起进房，但 Steam 启动失败: {exc}")
        return CommandResult(True, "电竞模式已进入；YY已发起进房")
    @staticmethod
    def _close_names(names: set[str]) -> int:
        killed=0
        for proc in psutil.process_iter(["name"]):
            try:
                if (proc.info.get("name") or "").lower() in names:proc.kill();killed+=1
            except (psutil.NoSuchProcess, psutil.AccessDenied):continue
        return killed
    @classmethod
    def _exit(cls) -> CommandResult:
        cs2=cls._close_names({"cs2.exe"});yy=cls._close_names(YY_PROCESS_NAMES);ok,msg=_set_default_audio_device(config.AUDIO_EXIT_DEVICE)
        if not ok:return CommandResult(False, f"退出电竞模式失败（音频）: {msg}")
        return CommandResult(True, f"电竞模式已退出，已关闭 CS2 {cs2} 个、YY {yy} 个进程")
