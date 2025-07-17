Work in python 3.10

Set up in anaconda:
- conda create -n ai-translator python=3.10
- conda activate ai-translator
- pip install -e . for dev or pip install .  for production

DONE: 
- lấy được text
- render được tiếng việt lên trên trang pdf 
- đúng bbox
- tạm thời đã có thể đọc được những chỗ thuần chữ

DOING:
- làm sao để merge các đoạn để giữ lại context
- fix nốt chiếu lên
    - fix nốt 1 số edge case không nằm trong đúng bbox
    - thêm chữ đậm nhạt
    - thêm xử lý phần ký tự toán học trên 1 dòng, ngoài dòng, etc
    - thêm hiển thị lùi đầu dòng với mỗi đoạn văn (nếu có thể) không thì cho các đoạn văn tách nhau ra
- thêm render hình ảnh

TO DO:
- fix hiện hên GUI đúng với format của văn bản gốc
- sửa dịch bằng gemini để chỉ cần cho api key
  
