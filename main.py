import argparse
import binascii
from functools import partial
import logging
import os
import re
import signal
import time
import requests
import concurrent.futures
from Crypto.Cipher import AES
from tqdm import tqdm

MAX_RETRIES = 5
RETRY_DELAY = 1

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class m3u8Download:

    def __init__(self, url):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3"
        }
        self.proxies = None 
        self.url = url
        self.base_url = url.rsplit("/", 1)[0] + "/"
        self.base_path = None
        self.m3u8_path = None
        self.key_path = None
        self.cancel_download = False
        self.executor = None

    def setHeaders(self, headers):
        self.headers = headers

    def setProxy(self, proxy):
        self.proxies = proxy

    def download_m3u8_file(self):
        response = requests.get(self.url, headers=self.headers, proxies=self.proxies)
        response.raise_for_status()
        m3u8_content = response.text
        output_path = os.path.join(self.base_path, self.base_path+'.m3u8')
        with open(output_path, "w") as f:
            f.write(m3u8_content)
        return output_path

    def download_key_file(self, url):
        response = requests.get(
            url, headers=self.headers, proxies=self.proxies, stream=True
        )
        response.raise_for_status()
        match = re.search(r'/([^/?]+)(?:\?.*)?$', url)
        match.group(1)
        output_path = os.path.join(self.base_path, match.group(1))
        with open(output_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=1024):
                if chunk:
                    f.write(chunk)
        return output_path
    
    def parse_m3u8_file(self, file_path):
        encryption_info = {}
        ts_files = []
        with open(file_path, "r") as f:
            lines = f.readlines()
            for line in lines:
                line = line.strip()
                if line.startswith("#EXT-X-KEY"):
                   match = re.search(r'METHOD=(.*?),URI="(.*?)",IV=(.*?)$', line)
                   if match:
                    method = match.group(1)
                    uri = match.group(2)
                    iv = match.group(3)
                    encryption_info["method"] = method
                    encryption_info["uri"] = uri
                    encryption_info["iv"] = iv[2:] 
                if not line.startswith("#"):
                    ts_files.append(line)
        return encryption_info, ts_files

    def download_and_decrypt(self, ts_file, key, iv):
        retries = 0
        while retries < MAX_RETRIES:
            try:
                if self.cancel_download:
                    return None
                if ts_file.startswith("http://") or ts_file.startswith("https://"):
                    url=ts_file
                else:
                    url = self.base_url + ts_file
                response = requests.get(url, headers=self.headers, proxies=self.proxies)
                encrypted_data = response.content
                cipher = AES.new(key, AES.MODE_CBC, iv)
                decrypted_data = cipher.decrypt(encrypted_data)
                return decrypted_data
            except Exception as exc:
                logger.error(f"{ts_file} generated an exception: {exc}")
                retries += 1
                if retries < MAX_RETRIES:
                    logger.info(f"Retrying ({retries}/{MAX_RETRIES})...")
                    time.sleep(RETRY_DELAY)
        # 如果达到最大重试次数仍然失败，则抛出异常
        raise RuntimeError(
            f"Failed to download and decrypt {ts_file} after {MAX_RETRIES} retries"
        )

    def cancel_download_handler(self, signum, frame):
        logger.info("\nDownload canceled.")
        self.cancel_download = True
        if self.executor:
            self.executor.shutdown(wait=False)

    def download(self, out_path=None):
        signal.signal(signal.SIGINT, self.cancel_download_handler)
        if out_path is None:
            out_path = os.path.splitext(os.path.basename(self.url))[0]
            os.makedirs(out_path, exist_ok=True)
        else:
            os.makedirs(out_path, exist_ok=True)
        self.base_path = out_path
        self.m3u8_path = self.download_m3u8_file()
        encryption_info, ts_files = self.parse_m3u8_file(self.m3u8_path)
        if encryption_info['uri'].startswith("http://") or encryption_info['uri'].startswith("https://"):
            key_url=encryption_info['uri']
        else:
            key_url = self.base_url + encryption_info["uri"]
        self.key_path = self.download_key_file(key_url)
        with open(self.key_path, "rb") as kf:
            key = kf.read()

        with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
            future_to_url = {
                executor.submit(
                    self.download_and_decrypt,
                    ts_url,
                    key,
                    binascii.unhexlify(encryption_info["iv"]),
                ): ts_url
                for ts_url in ts_files
            }
            for future in tqdm(
                concurrent.futures.as_completed(future_to_url), total=len(ts_files)
            ):
                if self.cancel_download:
                    logger.info("\nCancelling download...")
                    break
                ts_url = future_to_url[future]
                try:
                    decrypted_data = future.result()
                    temp_path = os.path.join(self.base_path, "temp")
                    if not os.path.exists(temp_path):
                        os.makedirs(temp_path)
                    if ts_url.startswith("http://") or ts_url.startswith("https://"):
                        match = re.match(r'^.*?/([^/?]+)(?:\?.*)?$', ts_url)
                        temp_ts_file = os.path.join(temp_path, match.group(1))
                    else:
                        temp_ts_file = os.path.join(temp_path, os.path.basename(ts_url))
                    with open(temp_ts_file, "wb") as f:
                        f.write(decrypted_data)
                except Exception as exc:
                    logger.error(f"{ts_url} generated an exception: {exc}")

        mp4_file = os.path.splitext(os.path.basename(self.url))[0] + ".mp4"
        mp4_file_path = os.path.join(self.base_path, mp4_file)
        with open(mp4_file_path, "wb") as output:
            for ts_file in ts_files:
                if ts_file.startswith("http://") or ts_file.startswith("https://"):
                    match = re.match(r'^.*?/([^/?]+)(?:\?.*)?$', ts_file)
                    temp_ts_file = os.path.join(temp_path, match.group(1))
                else:
                    temp_ts_file = os.path.join(temp_path, os.path.basename(ts_url))
                with open(temp_ts_file, "rb") as input:
                    output.write(input.read())

def main():
    parser = argparse.ArgumentParser(description="m3u8 Downloader")
    parser.add_argument("--url", help="URL of the m3u8 file to download")
    parser.add_argument("--proxy", help="Proxy server address (optional)")
    parser.add_argument(
        "--output-dir", help="Output directory for downloaded files (optional)"
    )
    args = parser.parse_args()
    downloader = m3u8Download(args.url)
    if args.proxy:
        downloader.setProxy(
            {
                "http": args.proxy,
                "https": args.proxy,
            }
        )
    if args.output_dir:
        output_dir = args.output_dir
    else:
        output_dir = None
    downloader.download(output_dir)


if __name__ == "__main__":
    main()