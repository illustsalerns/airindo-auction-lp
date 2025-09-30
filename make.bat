@echo off
setlocal enabledelayedexpansion

:: 入力ファイルと出力ファイルの指定
set INPUT=list.txt
set OUTPUT=auctions.json

:: JSON開始
echo [> %OUTPUT%

set first=1
for /f "usebackq tokens=1,* delims=" %%A in (`type %INPUT%`) do (
    set line=%%A
    :: ID行（例: w1201341836）
    echo !line!| findstr "^[a-z][0-9][0-9]*" >nul
    if not errorlevel 1 (
        set id=!line!
        set title=
        set date=
        set time=
        set img=
        set state=1
    ) else (
        if defined state (
            if !state! == 1 (
                :: タイトル行（A526 ...）
                set title=!line!
                for /f "tokens=1 delims= " %%t in ("!title!") do set img=%%t.jpg
                set state=2
            ) else if !state! == 2 (
                :: 終了日付行（09/26 (金)）
                echo !line!| findstr "/(" >nul
                if not errorlevel 1 (
                    set date=!line!
                    set state=3
                )
            ) else if !state! == 3 (
                :: 終了時刻行（23:24:00）
                echo !line!| findstr ":" >nul
                if not errorlevel 1 (
                    set time=!line!
                    set end=!date! !time!
                    if !first! == 1 (
                        set first=0
                    ) else (
                        echo ,>> %OUTPUT%
                    )
                    >> %OUTPUT% echo   {"id":"!id!","title":"!title!","img":"!img!","end":"!end!"}
                    set state=
                )
            )
        )
    )
)

:: JSON終了
echo ]>> %OUTPUT%

echo 完了: %OUTPUT% を作成しました。
endlocal
pause
