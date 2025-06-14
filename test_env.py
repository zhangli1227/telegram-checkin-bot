import sqlite3
from datetime import date

# 测试SQLite连接
def test_db_connection():
    conn = sqlite3.connect('data/test.db')
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS test (id INTEGER PRIMARY KEY, name TEXT)")
    cursor.execute("INSERT INTO test (name) VALUES ('test')")
    conn.commit()
    cursor.execute("SELECT * FROM test")
    result = cursor.fetchone()
    print(f"数据库测试结果: {result}")
    conn.close()

if __name__ == "__main__":
    test_db_connection()
    print("环境测试完成!")