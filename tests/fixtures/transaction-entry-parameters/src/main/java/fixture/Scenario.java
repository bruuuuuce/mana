package fixture;

import java.util.List;
import java.util.Map;
import org.springframework.stereotype.Service;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;

@Configuration
@EnableTransactionManagement(proxyTargetClass = true)
class Config {
    @Bean public DataSourceTransactionManager tx() { return new DataSourceTransactionManager(); }
}

@Service
class Entry {
    @Autowired Sink sink;
    @Autowired JdbcTemplate jdbc;
    @Transactional public void zero() { sink.required(); }
    @Transactional public void one(String value) { sink.required(); }
    @Transactional public void six(String a, int b, long c, boolean d, List<String> e, byte[] f) { sink.required(); }
    @Transactional public void arity() {}
    @Transactional public void arity(int value) {}
    @Transactional public void overload(String value) {}
    @Transactional public void overload(int value) {}
    @Transactional public void annotated(@Deprecated final String value) { sink.required(); }
    @Transactional public void generic(Map<String,List<Integer>> values) { sink.required(); }
    @Transactional public void unresolved(Missing value) {}
    @Transactional public <T> void variable(T value) {}
    @Transactional public void sentinel(String value) { factory("RECEIVER_SENTINEL_73").run("ARGUMENT_SENTINEL_73"); }
    @Transactional public void literal(String value) { jdbc.update("UPDATE SENTINEL_TABLE_73 SET v = 1"); }
    @Transactional public void shadow(Sink sink) { sink.required(); }
    @Transactional public void shadowJdbc(JdbcTemplate jdbc) { jdbc.update("UPDATE accounts SET v = 1"); }
    @Transactional public void parameterCall(String value) { sink.parameter(value); }
}

@Service
class Sink {
    @Transactional public void required() {}
    @Transactional public void parameter(String value) {}
}

class ExecutionTrap {
    static { if (true) throw new RuntimeException("TARGET_EXECUTION_SENTINEL_73"); }
}
