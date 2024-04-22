# M3U8 Downloader

---
- Support unencrypted downloads
- Support decryption AES-128
- Progress bar display
- Multithreading,Default 20 threads
- Retry on error
## Usage

---

```
usage: main.py [-h] [--url URL] [--proxy PROXY] [--output OUTPUT]  

m3u8 Downloader

options:
  -h, --help       show this help message and exit
  --url URL        URL of the m3u8 file to download
  --proxy PROXY    Proxy server address (optional)
  --output OUTPUT  Output directory for downloaded files (optional)
```

`python main.py --url http://xxxx/index.m3u8`
