package fixture;
import org.springframework.stereotype.Service;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.transaction.annotation.Transactional;
@Service class Entry {
    static class One {}
    class Two {}
    static class Three { static { System.getProperty("NESTED_SENTINEL_92"); } }
    @Autowired Sink sink;
    @Transactional public void zero() { sink.required(); }
    @Transactional public void six(String a, int b, long c, boolean d, String e, byte[] f) { sink.required(); }
    void unrelated() { new One(); }
}
