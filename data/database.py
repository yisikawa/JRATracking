from sqlalchemy import create_engine, Column, Integer, String, Float, Date, ForeignKey, UniqueConstraint, text, inspect as sa_inspect
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

Base = declarative_base()


class Race(Base):
    __tablename__ = 'races'

    id = Column(String, primary_key=True)
    name = Column(String)
    date = Column(Date)
    location = Column(String)
    course_type = Column(String)
    distance = Column(Integer)
    weather = Column(String)
    track_condition = Column(String)

    entries = relationship("Entry", back_populates="race", cascade="all, delete-orphan")
    results = relationship("Result", back_populates="race", cascade="all, delete-orphan")


class Horse(Base):
    __tablename__ = 'horses'

    id = Column(String, primary_key=True)
    name = Column(String)
    sex = Column(String)
    age = Column(Integer)
    sire = Column(String)
    dam = Column(String)

    entries = relationship("Entry", back_populates="horse")
    results = relationship("Result", back_populates="horse")


class Jockey(Base):
    __tablename__ = 'jockeys'

    id = Column(String, primary_key=True)   # netkeiba 騎手コード
    name = Column(String, nullable=False)

    entries = relationship('Entry', back_populates='jockey_obj')


class Entry(Base):
    __tablename__ = 'entries'

    id = Column(Integer, primary_key=True, autoincrement=True)
    race_id = Column(String, ForeignKey('races.id'))
    horse_id = Column(String, ForeignKey('horses.id'))
    jockey_id = Column(String, ForeignKey('jockeys.id'), nullable=True)

    bracket_number = Column(Integer)
    horse_number = Column(Integer)
    jockey = Column(String)
    trainer = Column(String)
    weight = Column(Float)

    race = relationship("Race", back_populates="entries")
    horse = relationship("Horse", back_populates="entries")
    jockey_obj = relationship('Jockey', back_populates='entries')

    __table_args__ = (UniqueConstraint('race_id', 'horse_id', name='_race_horse_uc'),)


class Result(Base):
    __tablename__ = 'results'

    id = Column(Integer, primary_key=True, autoincrement=True)
    race_id = Column(String, ForeignKey('races.id'))
    horse_id = Column(String, ForeignKey('horses.id'))

    rank = Column(Integer)
    time_seconds = Column(Float)
    odds = Column(Float)

    race = relationship("Race", back_populates="results")
    horse = relationship("Horse", back_populates="results")


def init_db(db_path='sqlite:///jra_data.db'):
    engine = create_engine(db_path)
    Base.metadata.create_all(engine)
    _migrate(engine)
    return sessionmaker(bind=engine)()


def _migrate(engine):
    """既存DBに新規カラム・テーブルを追加するマイグレーション"""
    inspector = sa_inspect(engine)

    with engine.connect() as conn:
        horse_cols = {c['name'] for c in inspector.get_columns('horses')}
        for col, col_type in [('sex', 'VARCHAR'), ('age', 'INTEGER'), ('sire', 'VARCHAR'), ('dam', 'VARCHAR')]:
            if col not in horse_cols:
                conn.execute(text(f'ALTER TABLE horses ADD COLUMN {col} {col_type}'))
                conn.commit()

        entry_cols = {c['name'] for c in inspector.get_columns('entries')}
        if 'jockey_id' not in entry_cols:
            conn.execute(text('ALTER TABLE entries ADD COLUMN jockey_id VARCHAR'))
            conn.commit()
