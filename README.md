# EzWinCommand v0.2

## 安装与启动

### 1. 准备环境

要求：

- Windows 10/11
- Python 3.13

解压发布包后，在 `EzWinCommand-server` 目录打开命令行，执行：

```bat
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### 2. 启动 Server

返回发布包根目录，双击：

```text
run-admin.bat
```

首次启动建议允许 Windows 防火墙和 UAC 请求。

不需要查看控制台时，可以双击：

```text
run-admin_no_console.bat
```

### 3. 打开管理页面

在运行 Server 的电脑上打开：

```text
http://localhost:8080
```

### 4. 安装 Android App

在 Android 手机上安装：

```text
android/app-release.apk
```

如果系统阻止安装，请允许当前浏览器或文件管理器安装未知来源应用。

### 5. 连接手机

确认手机和运行 Server 的电脑连接到同一个局域网。

在 Android App 中输入电脑的局域网地址，例如：

```text
http://192.168.1.10:8080
```

然后：

1. 在电脑管理页面点击“生成配对码”；
2. 在 Android App 输入页面显示的 4 位配对码；
3. 输入设备名称；
4. 完成配对。

### 6. 手机无法连接时

按顺序检查：

1. 电脑能否打开 `http://localhost:8080/ping`；
2. 手机和电脑是否连接同一个局域网；
3. App 中填写的是否为电脑局域网 IP；
4. Windows 防火墙是否允许 TCP 8080。

## 开机启动（可选）

双击：

```text
install-startup.bat
```

卸载开机启动：

```text
uninstall-startup.bat
```

## 配置文件

首次启动后，Server 会生成本机配置文件：

```text
EzWinCommand-server/config.local.env
```

不要删除或分享以下运行后生成的文件：

```text
EzWinCommand-server/config.local.env
EzWinCommand-server/agent/devices.json
EzWinCommand-server/agent/server_identity.json
```

本项目适合在可信局域网中使用，不建议直接暴露到公网。
