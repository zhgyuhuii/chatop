#!/bin/bash
# 设置命令行提示符显示 CUSTOM_USER 而非 abc
# 写入 /etc/profile.d，供 login 与 non-login shell 加载
if [ -n "${CUSTOM_USER}" ]; then
  mkdir -p /etc/profile.d
  cat > /etc/profile.d/99-custom-user-prompt.sh << 'PROFILE_EOF'
if [ -n "${CUSTOM_USER}" ]; then
  export PS1="${CUSTOM_USER}@\h:\w\$ "
fi
PROFILE_EOF
  chmod 644 /etc/profile.d/99-custom-user-prompt.sh
  # 确保 non-login shell（如 Konsole）也加载
  if ! grep -q '99-custom-user-prompt' /etc/bash.bashrc 2>/dev/null; then
    echo '[ -f /etc/profile.d/99-custom-user-prompt.sh ] && . /etc/profile.d/99-custom-user-prompt.sh' >> /etc/bash.bashrc
  fi
  echo "**** Custom prompt set to show ${CUSTOM_USER} ****"
fi
