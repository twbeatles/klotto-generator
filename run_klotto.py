import sys
import os

# 현재 디렉토리를 path에 추가하여 klotto 패키지를 찾을 수 있게 함
sys.path.insert(0, os.getcwd())

from klotto.main import main

if __name__ == '__main__':
    main()
