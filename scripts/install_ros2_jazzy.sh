#!/bin/bash
set -e

echo "=== Installing ROS2 Jazzy on Ubuntu 24.04 (Noble) ARM64 ==="

# Step 1: Ensure locale is UTF-8
echo "[1/6] Checking locale..."
sudo locale-gen en_US en_US.UTF-8
sudo update-locale LC_ALL=en_US.UTF-8 LANG=en_US.UTF-8
export LANG=en_US.UTF-8

# Step 2: Enable required repositories
echo "[2/6] Enabling Universe repository..."
sudo apt install -y software-properties-common
sudo add-apt-repository -y universe

# Step 3: Add ROS2 GPG key and repository
echo "[3/6] Adding ROS2 apt repository..."
sudo apt update && sudo apt install -y curl
sudo curl -sSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key -o /usr/share/keyrings/ros-archive-keyring.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] http://packages.ros.org/ros2/ubuntu $(. /etc/os-release && echo $UBUNTU_CODENAME) main" | sudo tee /etc/apt/sources.list.d/ros2.list > /dev/null

# Step 4: Install ROS2 Jazzy
echo "[4/6] Installing ROS2 Jazzy (ros-base + dev tools)..."
sudo apt update
sudo apt install -y ros-jazzy-ros-base ros-dev-tools

# Step 5: Source ROS2 setup in bashrc
echo "[5/6] Adding ROS2 sourcing to ~/.bashrc..."
if ! grep -q "source /opt/ros/jazzy/setup.bash" ~/.bashrc; then
    echo "" >> ~/.bashrc
    echo "# ROS2 Jazzy" >> ~/.bashrc
    echo "source /opt/ros/jazzy/setup.bash" >> ~/.bashrc
fi

# Step 6: Verify
echo "[6/6] Verifying installation..."
source /opt/ros/jazzy/setup.bash
echo "ROS_DISTRO=$ROS_DISTRO"
ros2 --help > /dev/null && echo "ros2 CLI working!"

echo ""
echo "=== ROS2 Jazzy installation complete! ==="
echo "Run 'source ~/.bashrc' or open a new terminal to use ROS2."
