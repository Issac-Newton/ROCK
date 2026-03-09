# Sandbox生命周期

## FSM

![image.png](https://alidocs.oss-cn-zhangjiakou.aliyuncs.com/res/ABmOoWbd3WveWOaw/img/56432f24-a7cc-4ddb-9049-d8be590ba3de.png)

## State

**PENDING**：sandbox提交后立即进入PENDING状态

**FAILED**：sandbox如因权限，镜像不存在，资源不足，rocklet启动失败等原因无法正常运行，进入FAILED

**RUNNING**：sandbox拉起后，rocklet可正常访问，进入RUNNING

**STOPPED**：容器被停掉，但容器存储还在。用户使用完成，手动调用stop；或者长时间无人使用该sandbox，进入STOPPED

**ARCHIVED**：容器存储被dump，可找回。sandbox在stop后，用户手动调用archive，或者配置了`auto_archive_seconds`（在STOPPED后），进行ARCHIVED

**DELETED**：容器存储被删掉，无法找回。sandbox在stop后，过了`auto_delete_seconds`，且未配置auto\_archive\_seconds，会自动删除容器存储，并进入DELETED

## archive实现

1.  拟采用docker commit进行。会将容器重新打成新镜像，并推送至ACR仓库。默认命名规则：`rock/rock-sandbox-archived:{sandbox-id}`