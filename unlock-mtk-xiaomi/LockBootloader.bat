@ECHO OFF

file\python file\mtk xflash seccfg lock

cls

echo Bootloader locked. Please disconnect the cable and press and hold the power button until the logo appears.
echo .
echo Xiaomiui | mtkclient
pause