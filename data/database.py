from sqlalchemy import create_engine, Column, Integer, String, Float, Date, ForeignKey, UniqueConstraint
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class Race(Base):
    __tablename__ = 'races'
    
    id = Column(String, primary_key=True) # JRA Race ID (e.g. 202301010101)
    name = Column(String)
    date = Column(Date)
    location = Column(String) # 東京, 中山, etc.
    course_type = Column(String) #芝, ダート, 障害
    distance = Column(Integer)
    weather = Column(String)
    track_condition = Column(String) # 良, 稍重, 重, 不良
    
    entries = relationship("Entry", back_populates="race")
    results = relationship("Result", back_populates="race")

class Horse(Base):
    __tablename__ = 'horses'
    
    id = Column(String, primary_key=True)
    name = Column(String)
    sire = Column(String) # 父
    dam = Column(String) # 母
    
    entries = relationship("Entry", back_populates="horse")
    results = relationship("Result", back_populates="horse")

class Entry(Base):
    __tablename__ = 'entries'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    race_id = Column(String, ForeignKey('races.id'))
    horse_id = Column(String, ForeignKey('horses.id'))
    
    bracket_number = Column(Integer) # 枠番
    horse_number = Column(Integer) # 馬番
    jockey = Column(String)
    trainer = Column(String)
    weight = Column(Float) # 斤量
    
    race = relationship("Race", back_populates="entries")
    horse = relationship("Horse", back_populates="entries")
    
    __table_args__ = (UniqueConstraint('race_id', 'horse_id', name='_race_horse_uc'),)

class Result(Base):
    __tablename__ = 'results'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    race_id = Column(String, ForeignKey('races.id'))
    horse_id = Column(String, ForeignKey('horses.id'))
    
    rank = Column(Integer) # 着順
    time_seconds = Column(Float) # 走破タイム(秒)
    odds = Column(Float) # 単勝オッズ
    
    race = relationship("Race", back_populates="results")
    horse = relationship("Horse", back_populates="results")

def init_db(db_path='sqlite:///jra_data.db'):
    engine = create_engine(db_path)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()
