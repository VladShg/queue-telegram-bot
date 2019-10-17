from sqlalchemy import create_engine, Column, Integer, String, ForeignKey, Boolean, Text, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm.session import object_session
from sqlalchemy.orm import sessionmaker, relationship

Base = declarative_base()


class Chat(Base):
    __tablename__ = "chat"

    chat_id = Column('chat_id', Integer, primary_key=True)
    default_time = Column('default_time', Integer, default=60)
    pin = Column('pin', Boolean, default=True)


class Queue(Base):
    __tablename__ = "queue"

    id = Column('id', Integer, primary_key=True)
    creator_id = Column('creator_id', Integer)
    message_id = Column('message_id', Integer, default=None)
    chat_id = Column('chat_id', Integer)
    pin_date = Column("pin_date", Integer)
    is_pinned = Column("is_pinned", Boolean, default=False)
    title = Column('title', Text)


class User(Base):
    __tablename__ = "user"

    id = Column('id', Integer, primary_key=True)
    username = Column("username", Text, default=None, primary_key=True)
    user_name = Column("user_name", Text)
    real_name = Column("real_name", Text, default=None)

    queue_record = relationship("QueueRecord", back_populates="user")


class QueueRecord(Base):
    __tablename__ = "queue_record"

    id = Column('id', Integer, primary_key=True)
    queue_id = Column("queue_id", Integer)
    position = Column("position", Integer, default=1)
    creator_id = Column("creator_id", Integer, default=None)

    user_id = Column(Integer, ForeignKey('user.id'))
    user = relationship("User", back_populates="queue_record")

    def remove_record(self):
        session = object_session(self)
        records = session.query(QueueRecord).filter(QueueRecord.queue_id == self.queue_id).all()
        for record in records:
            if record.position > self.position:
                record.position -= 1
                session.commit()

        session.delete(self)
        session.commit()


db_path = "data.db"  # sqlite path

engine = create_engine(f'sqlite:///{db_path}', echo=False)
Base.metadata.create_all(bind=engine)
Session = sessionmaker(bind=engine)

if __name__ == "__main__":
    print(f"{db_path} updated")
