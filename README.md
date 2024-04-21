# M3U8 Downloader
---
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

## Features

---

- Create a directory with m3u8 file name by default
- 20 threads are used for downloading by default
