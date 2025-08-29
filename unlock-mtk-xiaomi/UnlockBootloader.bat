@echo off

file\python file\mtk xflash seccfg unlock

cls

echo Bootloader unlocked. Please disconnect the cable and press and hold the power button until the logo appears. 
echo .
echo Xiaomiui | mtkclient
pause

