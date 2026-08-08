import os
import zipfile

# 要打包的文件夹（里面已经是所有依赖 + main.py + scf_bootstrap）
package_dir = "./package"
output_zip = "./deploy_with_deps.zip"

# 删除旧 zip
if os.path.exists(output_zip):
    os.remove(output_zip)

with zipfile.ZipFile(output_zip, 'w', zipfile.ZIP_DEFLATED) as zf:
    for root, dirs, files in os.walk(package_dir):
        for file in files:
            file_path = os.path.join(root, file)
            # 在 zip 中的路径（去掉 package_dir/ 前缀）
            arcname = os.path.relpath(file_path, package_dir)
            zf.write(file_path, arcname)

print(f"✅ 成功生成: {output_zip}")