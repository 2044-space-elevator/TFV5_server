# db.forum part 
import os

def test_forum(port_api : int, port_tcp : int):
    import db.forum
    D = db.forum.ForumDb("{}_forum.db".format(port_api), port_api, port_tcp)
    D.create_forum_table()
    D.create_forum("Touchfish Main Forum", 0, "This is the first forum.")
    D.send_post(0, 0, "Welcome to TouchFish V5!", "Nothing Here.")
    D.send_post(0, 0, "Welcome to TouchFish V5!(2)", "Nothing Here.")
    print("All Posts:")
    print(D.query_all_post(0))
    print("Deleted post 0")
    D.delete_post(0, 0)
    print(D.query_all_post(0))
    print("U0's forums are cleaned.")
    D.clean_user_content(0)
    print(D.query_forum_creater(0))
    D.conn.close()
    os.remove("{}_forum.db".format(port_api))