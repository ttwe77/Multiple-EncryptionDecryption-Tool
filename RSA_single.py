#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
one_time_rsa.py
交互式脚本：使用 openssl 做一次性 RSA 加密/解密流程（密钥默认保存在内存）。
依赖：openssl 可执行，pyperclip（可选，但推荐用于剪贴板）。
"""

import os
import sys
import subprocess
import tempfile
import base64
import hashlib
import getpass
import shutil
from pathlib import Path
import platform

def execute_command(command):
    """执行终端命令"""
    try:
        # 根据操作系统选择合适的shell
        if platform.system() == "Windows":
            result = subprocess.run(["cmd", "/c", command], 
                                  capture_output=True, 
                                  text=True, 
                                  encoding=sys.stdout.encoding,
                                  errors='replace')
        else:
            result = subprocess.run(["/bin/bash", "-c", command], 
                                  capture_output=True, 
                                  text=True)
        
        if result.stdout:
            print("输出:\n" + result.stdout)
        if result.stderr:
            print("错误:\n" + result.stderr)
        print(f"返回码: {result.returncode}")
        
    except Exception as e:
        print(f"执行命令时出错: {e}")

def clear_screen():
    # Windows
    if os.name == 'nt':
        os.system('cls')
    # Linux/Mac/其他
    else:
        os.system('clear')

# try pyperclip for clipboard operations
try:
    import pyperclip
    CLIP = True
except Exception:
    CLIP = False

# -------------------------
# Utilities
# -------------------------
def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def sha512_hex(data: bytes) -> str:
    return hashlib.sha512(data).hexdigest()

def run_openssl(args, input_bytes=None, check=True):
    cmd = ["openssl"] + args
    try:
        p = subprocess.run(cmd, input=input_bytes, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except FileNotFoundError:
        print("错误：未检测到 openssl 可执行，请安装 OpenSSL 并确保命令在 PATH 中。")
        sys.exit(1)
    if check and p.returncode != 0:
        raise RuntimeError(f"openssl failed: {' '.join(cmd)}\nstdout:\n{p.stdout.decode(errors='ignore')}\nstderr:\n{p.stderr.decode(errors='ignore')}")
    return p.stdout

def ensure_pyperclip():
    if not CLIP:
        print("注意：当前系统没有安装 pyperclip，剪贴板功能不可用。")
        print("可以通过 `pip install pyperclip` 安装。")
        return False
    return True

def copy_to_clipboard(text: str):
    if ensure_pyperclip():
        pyperclip.copy(text)
        print("[已复制到剪贴板]")
    else:
        print("[未复制：pyperclip 不可用]")

def paste_from_clipboard() -> str:
    if ensure_pyperclip():
        return pyperclip.paste()
    else:
        raise RuntimeError("剪贴板不可用 (pyperclip 未安装)")

# Temporary file helper for passing keys to openssl (we keep keys in memory but openssl needs files)
def write_temp_file(data: bytes, suffix=""):
    tf = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tf.write(data)
    tf.flush()
    tf.close()
    return tf.name

def remove_file_silent(path):
    try:
        os.unlink(path)
    except Exception:
        pass

# -------------------------
# RSA key generation
# -------------------------
def generate_rsa_keypair(bits: int):
    # Use openssl to generate unencrypted private key PEM and derive public key PEM
    print(f"正在生成 RSA-{bits} 密钥对（使用 openssl，可能需要一些时间）...")
    priv_pem = run_openssl(["genpkey", "-algorithm", "RSA", "-pkeyopt", f"rsa_keygen_bits:{bits}"])
    # genpkey returns a private key PEM
    # extract public key
    tmp_priv = write_temp_file(priv_pem, suffix=".pem")
    try:
        pub_pem = run_openssl(["pkey", "-in", tmp_priv, "-pubout"])
    finally:
        remove_file_silent(tmp_priv)
    # 去除末尾所有空白字符（包括换行、空格等）
    priv_pem = priv_pem.rstrip()
    pub_pem = pub_pem.rstrip()
    print("密钥生成完成（密钥目前仅保存在内存中）。")
    return priv_pem, pub_pem

# -------------------------
# RSA encrypt/decrypt (OAEP SHA256)
# -------------------------
def rsa_encrypt_with_pubkey(pub_pem_bytes: bytes, plaintext: bytes) -> bytes:
    """使用公钥对短消息进行 RSA OAEP-SHA256 加密。返回 base64 编码的结构：首行 RSA-ENC then base64"""
    tmp_pub = write_temp_file(pub_pem_bytes, suffix=".pub.pem")
    tmp_in = write_temp_file(plaintext, suffix=".bin")
    try:
        # openssl pkeyutl -encrypt -pubin -inkey pub.pem -pkeyopt rsa_padding_mode:oaep -pkeyopt rsa_oaep_md:sha256
        out = run_openssl([
            "pkeyutl", "-encrypt", "-pubin", "-inkey", tmp_pub,
            "-in", tmp_in,
            "-pkeyopt", "rsa_padding_mode:oaep", "-pkeyopt", "rsa_oaep_md:sha256"
        ])
    finally:
        remove_file_silent(tmp_pub)
        remove_file_silent(tmp_in)
    # wrap with header for detection
    wrapped = b"RSA-ENC\n" + base64.b64encode(out)
    return wrapped

def rsa_decrypt_with_privkey(priv_pem_bytes: bytes, ciphertext_b64: bytes) -> bytes:
    tmp_priv = write_temp_file(priv_pem_bytes, suffix=".priv.pem")
    tmp_in = write_temp_file(base64.b64decode(ciphertext_b64), suffix=".enc")
    try:
        out = run_openssl([
            "pkeyutl", "-decrypt", "-inkey", tmp_priv,
            "-in", tmp_in,
            "-pkeyopt", "rsa_padding_mode:oaep", "-pkeyopt", "rsa_oaep_md:sha256"
        ])
    finally:
        remove_file_silent(tmp_priv)
        remove_file_silent(tmp_in)
    return out

def rsa_max_plain_bytes(bits: int) -> int:
    # For OAEP with SHA256: max = k - 2*hLen - 2, where k = key bytes, hLen = 32 for SHA256
    k = bits // 8
    h = 32
    return k - 2 * h - 2

# -------------------------
# AES helper (openssl enc)
# -------------------------
def aes256_encrypt_bytes(passphrase: str, data: bytes) -> bytes:
    # We will produce "AES256-ENC\n" + base64(ciphertext)
    # Use openssl enc -aes-256-cbc -salt -pass pass:...
    p = subprocess.Popen(["openssl", "enc", "-aes-256-cbc", "-salt", "-pass", f"pass:{passphrase}"],
                         stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    out, err = p.communicate(data)
    if p.returncode != 0:
        raise RuntimeError(f"AES encrypt failed: {err.decode(errors='ignore')}")
    wrapped = b"AES256-ENC\n" + base64.b64encode(out)
    return wrapped

def aes256_decrypt_bytes(passphrase: str, payload_b64: bytes) -> bytes:
    raw = base64.b64decode(payload_b64)
    p = subprocess.Popen(["openssl", "enc", "-d", "-aes-256-cbc", "-salt", "-pass", f"pass:{passphrase}"],
                         stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    out, err = p.communicate(raw)
    if p.returncode != 0:
        raise RuntimeError(f"AES decrypt failed: {err.decode(errors='ignore')}")
    return out

# -------------------------
# Hybrid file encryption: AES file, RSA-encrypt AES key
# -------------------------
import secrets
def efile_hybrid_encrypt(pub_pem_bytes: bytes, file_path: str):
    # read file bytes
    with open(file_path, "rb") as f:
        data = f.read()
    # random AES key and iv
    key = secrets.token_bytes(32)  # AES-256 key
    iv = secrets.token_bytes(16)
    # encrypt data using openssl with raw key/iv: openssl enc -aes-256-cbc -K <hexkey> -iv <hexiv>
    hexK = key.hex()
    hexIV = iv.hex()
    p = subprocess.Popen(["openssl", "enc", "-aes-256-cbc", "-K", hexK, "-iv", hexIV],
                         stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    out, err = p.communicate(data)
    if p.returncode != 0:
        raise RuntimeError(f"file AES encryption failed: {err.decode(errors='ignore')}")
    # Now prepare key+iv blob and encrypt with RSA public key
    keyblob = key + iv
    # encrypt keyblob with RSA pub
    tmp_pub = write_temp_file(pub_pem_bytes, suffix=".pub.pem")
    tmp_keyblob = write_temp_file(keyblob, suffix=".bin")
    try:
        enc_key = run_openssl([
            "pkeyutl", "-encrypt", "-pubin", "-inkey", tmp_pub, "-in", tmp_keyblob,
            "-pkeyopt", "rsa_padding_mode:oaep", "-pkeyopt", "rsa_oaep_md:sha256"
        ])
    finally:
        remove_file_silent(tmp_pub)
        remove_file_silent(tmp_keyblob)
    # package: VERSION|base64(enc_key)|base64(ciphertext)
    package = b"HYBRID-RSA-AES\n" + base64.b64encode(enc_key) + b"\n" + base64.b64encode(out)
    out_path = file_path + ".enc"
    with open(out_path, "wb") as f:
        f.write(package)
    # also copy package to clipboard
    try:
        copy_to_clipboard(package.decode())
    except Exception:
        pass
    print(f"已生成加密文件：{out_path}，并尝试复制到剪贴板（若可用）。")
    return out_path

def dfile_hybrid_decrypt(priv_pem_bytes: bytes, enc_file_path: str, out_path: str = None):
    with open(enc_file_path, "rb") as f:
        raw = f.read()
    if not raw.startswith(b"HYBRID-RSA-AES\n"):
        raise RuntimeError("不是本程序生成的 HYBRID-RSA-AES 加密文件。")
    parts = raw.split(b"\n", 2)
    enc_key_b64 = parts[1]
    ciphertext_b64 = parts[2]
    enc_key = base64.b64decode(enc_key_b64)
    # decrypt enc_key with our private key
    tmp_priv = write_temp_file(priv_pem_bytes, suffix=".priv.pem")
    tmp_enc = write_temp_file(enc_key, suffix=".bin")
    try:
        keyblob = run_openssl([
            "pkeyutl", "-decrypt", "-inkey", tmp_priv, "-in", tmp_enc,
            "-pkeyopt", "rsa_padding_mode:oaep", "-pkeyopt", "rsa_oaep_md:sha256"
        ])
    finally:
        remove_file_silent(tmp_priv)
        remove_file_silent(tmp_enc)
    if len(keyblob) != 48:
        raise RuntimeError("解密的对称密钥尺寸异常。")
    key = keyblob[:32]
    iv = keyblob[32:]
    # decrypt ciphertext
    cipher_raw = base64.b64decode(ciphertext_b64)
    hexK = key.hex()
    hexIV = iv.hex()
    p = subprocess.Popen(["openssl", "enc", "-d", "-aes-256-cbc", "-K", hexK, "-iv", hexIV],
                         stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    out, err = p.communicate(cipher_raw)
    if p.returncode != 0:
        raise RuntimeError(f"file AES decryption failed: {err.decode(errors='ignore')}")
    if out_path is None:
        out_path = enc_file_path.replace(".enc", ".dec")
    with open(out_path, "wb") as f:
        f.write(out)
    print(f"解密完成，输出到：{out_path}")
    return out_path

# -------------------------
# Import / Export public key logic
# -------------------------
def import_public_key_from_text(text: str, my_priv_pem: bytes = None):
    """
    自动识别 text 是否是：
      - 纯 PEM 公钥（以 -----BEGIN PUBLIC KEY----- 开头）
      - AES256-ENC 包装（以首行 AES256-ENC）
      - RSA-ENC 包装（以首行 RSA-ENC） -> 试图用我的私钥解密以取得原始公钥
    返回原始公钥 bytes
    """
    t = text.strip()
    # check PEM
    if t.startswith("-----BEGIN PUBLIC KEY-----"):
    # 提取BASE64编码的公钥数据
        lines = []
        in_body = False
        for line in t.splitlines():
            line = line.strip()
            if line == "-----BEGIN PUBLIC KEY-----":
                in_body = True
                continue
            if line == "-----END PUBLIC KEY-----":
                break
            if in_body and line:  # 只收集非空行
                lines.append(line)
        # 合并所有BASE64行并解码
        base64_data = ''.join(lines)
        try:
            raw_pubkey = base64.b64decode(base64_data)
        except Exception as e:
            print(f"Base64解码失败: {e}")
            # 如果解码失败，回退到计算原始文本的哈希
            raw = t.encode()
            sha256v = sha256_hex(raw)
            sha512v = sha512_hex(raw)
            print(f"识别为 PEM 公钥（解码失败，使用原始文本）。SHA256: {sha256v}  SHA512: {sha512v}")
            return raw, sha256v, sha512v
        
        # 计算公钥数据的哈希（这才是真正有意义的哈希）
        raw = t.encode()
        sha256v = sha256_hex(raw)
        sha512v = sha512_hex(raw)
        print(f"[PEM] 公钥识别完成")
        print(f"├─ 状态:  解码失败（使用原始文本）")
        print(f"├─ SHA256: {sha256v}")
        print(f"└─ SHA512: {sha512v}")
        print(f"公钥长度: {len(raw_pubkey)} 字节")
        
        # 返回原始PEM文本和公钥数据的哈希
        return t.encode(), sha256v, sha512v
    # check AES wrapper
    if t.startswith("AES256-ENC"):
        print("识别为 AES256 封装公钥。需要输入 AES 密码以解密以获得原始公钥文本。")
        b64 = t.split("\n",1)[1].strip()
        passphrase = getpass.getpass("请输入用于 AES256 加密的密码：")
        try:
            raw = aes256_decrypt_bytes(passphrase, b64.encode())
        except Exception as e:
            raise RuntimeError(f"AES 解密失败：{e}")
        sha256v = sha256_hex(raw)
        sha512v = sha512_hex(raw)
        print(f"AES 解包成功。导入的公钥 SHA256: {sha256v}  SHA512: {sha512v}")
        return raw, sha256v, sha512v
    # check RSA wrapper (encrypted with our public/private scheme)
    if t.startswith("RSA-ENC"):
        if my_priv_pem is None:
            raise RuntimeError("检测到 RSA-ENC 包装，但本地没有私钥用于解密以恢复原始公钥。")
        b64 = t.split("\n",1)[1].strip()
        try:
            raw = rsa_decrypt_with_privkey(my_priv_pem, b64.encode())
        except Exception as e:
            raise RuntimeError(f"使用本地私钥解 RSA-ENC 失败：{e}")
        sha256v = sha256_hex(raw)
        sha512v = sha512_hex(raw)
        print(f"RSA 封装解包成功。导入的公钥 SHA256: {sha256v}  SHA512: {sha512v}")
        return raw, sha256v, sha512v
    # otherwise unknown
    raise RuntimeError("无法识别导入内容的格式（既不是 PEM，也不是 AES256-ENC 或 RSA-ENC）。")

# -------------------------
# Main interactive flow
# -------------------------
def print_guide_if_exists():
    guide_path = Path("guide.md")
    if guide_path.exists():
        print("\n====== guide.md 内容如下 ======\n")
        print(guide_path.read_text(encoding="utf-8"))
        print("====== 结束 ======\n")
    else:
        print("工作目录下未找到 guide.md 。请将教程文件放在当前工作目录，并命名为 guide.md 。")

def main():
    my_priv = None  # bytes PEM
    my_pub = None   # bytes PEM
    their_pub = None  # bytes PEM (imported)
    their_pub_raw_text = None

    while True:
        print("\n主菜单：请选择：")
        print("1. 新建一次性加密项")
        print("2. 使用教程（打印工作目录下的 guide.md）")
        print("0. 退出")
        choice = input("选择: ").strip()
        if choice == "0":
            print("退出。")
            return
        if choice == "2":
            print_guide_if_exists()
            continue
        if choice != "1":
            print("请输入 1 或 2 或 0。")
            continue

        # 1: generate
        clear_screen()
        print("请选择使用的算法：")
        print("1. RSA2048")
        print("2. RSA4096")
        print("3. RSA8192")
        alg = input("选择: ").strip()
        bits_map = {"1": 2048, "2": 4096, "3": 8192}
        if alg not in bits_map:
            print("无效选择，返回主菜单。")
            continue
        bits = bits_map[alg]
        try:
            my_priv, my_pub = generate_rsa_keypair(bits)
        except Exception as e:
            print("生成密钥失败：", e)
            continue

        # After generation menu (no automatic jump)
        while True:
            print("\n生成完成，选择：")
            print("1. 导出公钥")
            print("2. 导入对方公钥（从剪贴板或文件）")
            print("3. 进入加密/解密模式")
            print("back. 返回上一级（重新选择算法或主菜单）")
            sub = input("输入: ").strip()
            clear_screen()
            if sub == "back":
                break
            if sub == "1":
                # export public key options
                print("\n导出公钥：选择导出方式（导出不会自动删除内存中的密钥）：")
                print("1. 复制公钥明文（不推荐）")
                print("2. 用 AES256 加密公钥并复制（需要输入密码）")
                opt = input("选择: ").strip()
                raw_pub = my_pub
                # compute hashes of original raw public key
                sha256v = sha256_hex(raw_pub)
                sha512v = sha512_hex(raw_pub)
                if opt == "1":
                    # copy plain
                    try:
                        copy_to_clipboard(raw_pub.decode())
                    except Exception:
                        pass
                    print("已输出公钥（明文）并复制（若可用）。")
                elif opt == "2":
                    passwd = getpass.getpass("请输入用于 AES256 加密的密码（会用于加密公钥）：")
                    wrapped = aes256_encrypt_bytes(passwd, raw_pub)
                    try:
                        copy_to_clipboard(wrapped.decode())
                    except Exception:
                        pass
                    print("公钥已用 AES256 加密并复制（若剪贴板可用）。")
                else:
                    print("无效选项。")
                print(f"公钥原文的 SHA256: {sha256v}")
                print(f"公钥原文的 SHA512: {sha512v}")
                # after export, stay in this menu
                continue
            elif sub == "2":
                # import other's public key from clipboard or file
                print("\n导入公钥：请选择来源：")
                print("1. 从剪贴板导入")
                print("2. 从文件导入（请输入路径）")
                src = input("选择: ").strip()
                try:
                    if src == "1":
                        if not CLIP:
                            print("剪贴板不可用（未安装 pyperclip）。请使用从文件导入。")
                            continue
                        txt = paste_from_clipboard()
                        try:
                            raw, s256, s512 = import_public_key_from_text(txt, my_priv_pem=my_priv)
                        except Exception as e:
                            print("导入失败：", e)
                            continue
                    elif src == "2":
                        path = input("请输入文件路径: ").strip()
                        if not os.path.exists(path):
                            print("文件不存在。若有引号请将其移除")
                            continue
                        txt = Path(path).read_text(encoding="utf-8")
                        try:
                            raw, s256, s512 = import_public_key_from_text(txt, my_priv_pem=my_priv)
                        except Exception as e:
                            print("导入失败：", e)
                            continue
                    else:
                        print("无效选择。")
                        continue
                except Exception as e:
                    print("导入过程出现错误：", e)
                    continue
                # success
                their_pub = raw
                their_pub_raw_text = raw
                print("导入完成。你现在可在加密/解密模式中使用该公钥进行加密。")
                continue
            elif sub == "3":
                # enter encrypt/decrypt mode
                print("\n进入加解密模式。输入 'help' 查看命令；输入 'back' 返回上一级菜单；输入 'exit' 退出程序。")
                while True:
                    cmd = input("\n[enc/dec] > ").rstrip("\n")
                    if cmd == "":
                        # decrypt clipboard content
                        print("[操作] 从剪贴板读取并尝试解密...")
                        if not CLIP:
                            print("剪贴板不可用。请安装 pyperclip 或使用 dfile 从文件解密。")
                            continue
                        raw_text = paste_from_clipboard()
                        if not raw_text:
                            print("剪贴板为空。")
                            continue
                        t = raw_text.strip()
                        try:
                            if t.startswith("AES256-ENC"):
                                b64 = t.split("\n",1)[1].strip()
                                passwd = getpass.getpass("请输入用于 AES 解密的密码：")
                                plain = aes256_decrypt_bytes(passwd, b64.encode())
                                print("解密后明文：\n")
                                try:
                                    print(plain.decode())
                                except Exception:
                                    print("[二进制数据已解密，写入文件 output.dec]")
                                    with open("output.dec", "wb") as f:
                                        f.write(plain)
                                        print("已写入 output.dec")
                            elif t.startswith("RSA-ENC"):
                                if my_priv is None:
                                    print("本地无私钥，无法解 RSA-ENC。")
                                    continue
                                b64 = t.split("\n",1)[1].strip()
                                plain = rsa_decrypt_with_privkey(my_priv, b64.encode())
                                print("RSA 解密后结果：\n")
                                try:
                                    print(plain.decode())
                                except Exception:
                                    print("[二进制数据已解密，写入文件 output.dec]")
                                    with open("output.dec", "wb") as f:
                                        f.write(plain)
                                        print("已写入 output.dec")
                            elif t.startswith("HYBRID-RSA-AES"):
                                # likely a packaged file as text; save to tmp file and call dfile
                                tmp = write_temp_file(t.encode(), suffix=".hybrid")
                                try:
                                    outp = dfile_hybrid_decrypt(my_priv, tmp)
                                    print(f"写入到临时解密路径：{outp}")
                                finally:
                                    remove_file_silent(tmp)
                            else:
                                print("剪贴板内容没有检测到密文")
                        except Exception as e:
                            print("解密失败：", e)
                        continue
                    if cmd.lower() in ("back",):
                        break
                    if cmd.startswith("exec"):
                      # 处理 "exec" 后面可能没有空格的情况
                        if cmd.lower() == "exec":
                            print("使用方法: exec <命令>")
                            print("例如: exec dir (Windows) 或 exec ls -la (Linux/Mac)")
                            continue
                        command_to_run = cmd[5:].strip()  # 去掉 "exec "
                        if command_to_run:
                            execute_command(command_to_run)
                        else:
                            print("请输入要执行的命令，例如: exec ls -la")
                        continue

                    if cmd.lower() in ("exit", "quit"):
                        print("退出程序。")
                        sys.exit(0)
                    if cmd.lower() == "clear":
                        clear_screen()
                        continue
                    if cmd.lower() == "help":
                        print("""
┌───────────────── 命令说明（加解密模式） ─────────────────┐

  [空行]        从剪贴板读取并尝试解密

  输入单行文本  使用对方公钥进行 RSA 加密
                * 明文过长时会报错

  more          进入多行输入模式（以单独一行 . 结束）
                对完整文本进行 RSA 加密并复制密文

  efile <路径>  加密文件（仅RSA加密）
                生成：<路径>.enc
                自动复制包装后的文本

  dfile <路径>  解密文件

  epublic       导出本地公钥 → my_public.pem（当前目录）

  esecret       导出本地私钥 → my_private.pem（当前目录）

  back          返回上一级菜单

  exit          退出程序

  clear         清空终端

└───────────────────────────────────────────────────────┘
""")
                        continue
                    if cmd.startswith("efile "):
                        parts = cmd.split(" ",1)
                        path = parts[1].strip()
                        if not os.path.exists(path):
                            print("文件不存在。若有引号请将其移除")
                            continue
                        if their_pub is None:
                            print("未导入对方公钥，无法加密文件。请先导入对方公钥。")
                            continue
                        try:
                            outp = efile_hybrid_encrypt(their_pub, path)
                        except Exception as e:
                            print("efile 加密失败：", e)
                        continue
                    if cmd.startswith("dfile "):
                        parts = cmd.split(" ",1)
                        path = parts[1].strip()
                        if not os.path.exists(path):
                            print("文件不存在。若有引号请将其移除")
                            continue
                        if my_priv is None:
                            print("本地无私钥，无法解密文件。")
                            continue
                        try:
                            outp = dfile_hybrid_decrypt(my_priv, path)
                        except Exception as e:
                            print("dfile 解密失败：", e)
                        continue
                    if cmd.strip().lower() == "more":
                        print("进入多行输入（以单独一行“.”再按Enter结束）：")
                        lines = []
                        while True:
                            ln = input()
                            if ln.strip() == ".":
                                break
                            lines.append(ln)
                        text = "\n".join(lines).encode()
                        # require their_pub
                        if their_pub is None:
                            print("未导入对方公钥，无法加密。")
                            continue
                        # check RSA length
                        maxb = rsa_max_plain_bytes(len(their_pub)*8) if False else None
                        # Instead of computing from their_pub bytes (which is PEM), compute using bits from our generated key size
                        # simulate by deriving k from my_pub? Simpler: check against their public's modulus by reading via openssl?
                        # We'll approximate by using our own private key size if available; else use 2048
                        try:
                            if their_pub:
                                # attempt to determine their key bits by writing and calling openssl rsa -pubin -in pub.pem -text -noout
                                tmp_pubf = write_temp_file(their_pub, suffix=".pub.pem")
                                try:
                                    info = run_openssl(["pkey", "-pubin", "-in", tmp_pubf, "-text"], check=False).decode(errors="ignore")
                                    # search for "RSA Public-Key: (4096 bit)" pattern
                                    import re
                                    m = re.search(r"RSA Public-Key:\s*\((\d+)\s*bit\)", info)
                                    bits_detected = int(m.group(1)) if m else None
                                finally:
                                    remove_file_silent(tmp_pubf)
                            else:
                                bits_detected = None
                        except Exception:
                            bits_detected = None
                        if bits_detected is None:
                            bits_detected = 2048
                        max_plain = rsa_max_plain_bytes(bits_detected)
                        if len(text) > max_plain:
                            print(f"文本长度 {len(text)} 字节，超过对方 RSA-{bits_detected} 单次可加密上限 {max_plain} 字节。请缩短或使用 efile。")
                            continue
                        try:
                            enc = rsa_encrypt_with_pubkey(their_pub, text)
                            copy_to_clipboard(enc.decode())
                            print("加密成功，密文已复制到剪贴板（若可用）。")
                        except Exception as e:
                            print("RSA 加密失败：", e)
                        continue
                    if cmd.strip().lower() == "epublic":
                        if my_pub is None:
                            print("无本地公钥。")
                            continue
                        p = Path("my_public.pem")
                        p.write_bytes(my_pub)
                        print(f"已导出公钥到 {p.resolve()}")
                        continue
                    if cmd.strip().lower() == "esecret":
                        if my_priv is None:
                            print("无本地私钥。")
                            continue
                        p = Path("my_private.pem")
                        p.write_bytes(my_priv)
                        print(f"已导出私钥到 {p.resolve()}")
                        continue
                    # otherwise treat cmd as single-line plaintext to encrypt
                    plaintext = cmd.encode()
                    if their_pub is None:
                        print("未导入对方公钥，无法加密。请先导入对方公钥。")
                        continue
                    # try to detect their key size and enforce RSA max bytes
                    try:
                        tmp_pubf = write_temp_file(their_pub, suffix=".pub.pem")
                        try:
                            info = run_openssl(["pkey", "-pubin", "-in", tmp_pubf, "-text"], check=False).decode(errors="ignore")
                            import re
                            m = re.search(r"RSA Public-Key:\s*\((\d+)\s*bit\)", info)
                            bits_detected = int(m.group(1)) if m else 2048
                        finally:
                            remove_file_silent(tmp_pubf)
                    except Exception:
                        bits_detected = 2048
                    max_plain = rsa_max_plain_bytes(bits_detected)
                    if len(plaintext) > max_plain:
                        print(f"明文过长（{len(plaintext)} 字节），超过 RSA-{bits_detected} 单次上限 {max_plain} 字节。请缩短或使用 efile。")
                        continue
                    try:
                        enc = rsa_encrypt_with_pubkey(their_pub, plaintext)
                        copy_to_clipboard(enc.decode())
                        print("加密成功，密文已复制到剪贴板（若可用）。")
                    except Exception as e:
                        print("RSA 加密失败：", e)
                # end encrypt/decrypt while
                continue
            else:
                print("无效选项，请选择 1/2/3/back。")
                continue

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n已中断，退出。")
