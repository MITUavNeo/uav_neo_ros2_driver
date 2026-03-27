import glob
from setuptools import find_packages, setup

package_name = 'uav_neo_ros2_driver'

setup(
    name=package_name,
    version='0.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        ('share/' + package_name + '/launch',
            glob.glob('launch/*.launch.py')),
        ('share/' + package_name + '/config',
            glob.glob('config/*.yaml')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='uav',
    maintainer_email='uav@todo.todo',
    description='ROS2 driver for UAV Neo',
    license='TODO: License declaration',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
        ],
    },
)
