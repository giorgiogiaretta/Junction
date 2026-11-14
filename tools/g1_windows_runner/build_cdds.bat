@echo off
call "C:\Program Files\Microsoft Visual Studio\18\Insiders\VC\Auxiliary\Build\vcvars64.bat"
set TP=C:\Users\giorg\Desktop\aaltonomous-humanoid\third_party
if not exist %TP%\cyclonedds git clone -q https://github.com/eclipse-cyclonedds/cyclonedds %TP%\cyclonedds
git -C %TP%\cyclonedds checkout -q 5041f3560c088c99e5088b2b8520b69169621196
if not exist %TP%\cyclonedds\build mkdir %TP%\cyclonedds\build
cd /d %TP%\cyclonedds\build
cmake .. -G "NMake Makefiles" -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX=%TP%\cyclonedds\install -DBUILD_EXAMPLES=OFF -DBUILD_TESTING=OFF -DBUILD_IDLC=ON -DENABLE_SSL=OFF -DENABLE_SECURITY=OFF || exit /b 1
cmake --build . --target install || exit /b 1
set CYCLONEDDS_HOME=%TP%\cyclonedds\install
py -3.11 -m pip install cyclonedds==0.10.5 || exit /b 1
py -3.11 -c "import cyclonedds.domain; print('CYCLONEDDS OK')"
