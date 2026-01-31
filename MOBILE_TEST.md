# 用手機測試網站

## 步驟

### 1. 啟動開發環境

- **Docker**：`./enter_dev_env.sh up` 或 `./enter_dev_env.sh build`
- **本機**：終端機 1 跑後端、終端機 2 跑前端（見 README）

### 2. 查電腦的區網 IP

手機和電腦要在**同一個 Wi‑Fi** 下。

**Windows（PowerShell 或 CMD）：**
```powershell
ipconfig
```
在「無線區域網路介面卡」或「乙太網路」裡找 **IPv4 位址**，例如 `192.168.1.100`。

**Git Bash（Windows）：**  
Git Bash 不支援 `hostname -I`，請用下面其中**一個**指令（不要整段一起複製）：

只顯示第一個 IPv4：
```bash
ipconfig | grep -i "IPv4" | head -1 | sed 's/.*: //' | tr -d ' \r'
```

或直接看完整列表再手動找 IP：
```bash
ipconfig
```

**WSL / Linux：**
```bash
hostname -I | awk '{print $1}'
```

### 3. 用手機開啟網站

1. 手機連上**同一個 Wi‑Fi**。
2. 手機瀏覽器網址列輸入：
   ```
   http://<你的電腦IP>:5173
   ```
   例如：`http://192.168.1.100:5173`

### 4. 若無法連線

- 確認電腦防火牆有放行 **port 5173**（及 3001，若手機直連後端）。
- 確認前端有啟動且顯示 `Local: http://0.0.0.0:5173`（Vite 已綁定區網）。
- Docker 時，確認 `docker-compose.dev.yml` 有 `ports: - "5173:5173"`。

## 用 ngrok 測試店家掃描街友 QR Code

若用 **ngrok** 轉發前端，QR Code 裡的網址會變成你開網頁時的那個網址（例如 localhost）。  
店家用手機掃 QR 時會開到 localhost，在手機上會失敗。

**做法：** 在專案根目錄的 `client` 底下新增或編輯 `.env`，設定公開網址（不要加結尾斜線）：

```env
VITE_PUBLIC_URL=https://你的ngrok網址.ngrok-free.dev
```

例如：

```env
VITE_PUBLIC_URL=https://unnormalized-noncommunistically-dangelo.ngrok-free.dev
```

存檔後**重啟前端**（`npm run dev` 或 Docker 前端容器），再重新產生或重新開啟街友 QR Code 頁面。  
之後 QR Code 會指向 ngrok 網址，店家用手機掃描即可正常開啟。

- 若沒設 `VITE_PUBLIC_URL`，會用目前開網頁的網址（`window.location.origin`）。
- 每次 ngrok 網址變了，記得更新 `.env` 並重啟前端。

## 注意

- 使用 **http**，不要用 https（本機開發通常沒憑證）。
- 登入等 API 會經由前端的 proxy 打到後端，無須在手機改網址。
- 若電腦 IP 會變（DHCP），每次重連 Wi‑Fi 後可能要重新查 IP 再開一次網址。
