import glob

from setuptools import find_packages, setup

package_name = 'uav_neo_ros2_driver'

setup(
    name=package_name,
    version='1.4.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        ('share/' + package_name + '/launch',
            glob.glob('launch/*.launch.py')),
        ('share/' + package_name + '/config',
            glob.glob('config/*.yaml')),
        ('share/' + package_name + '/models',
            glob.glob('models/*')),
        ('share/' + package_name + '/scripts',
            glob.glob('scripts/*.sh') + glob.glob('scripts/*.py')),
        ('share/' + package_name + '/services',
            glob.glob('scripts/*.service')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='uav',
    maintainer_email='uav@todo.todo',
    description='ROS2 driver for UAV Neo',
    license='GPL-3.0-or-later',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'edgetpu_node = uav_neo_ros2_driver.edgetpu_node:main',
            'mux_node = uav_neo_ros2_driver.mux_node:main',
            'gamepad_node = uav_neo_ros2_driver.gamepad:main',
        ],
    },
)
